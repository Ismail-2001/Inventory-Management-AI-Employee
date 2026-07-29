"""
Inventory Agent - AI Employee #2
Demand Forecasting, Reorder Optimization, Stock Analysis
"""

import os
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from shared.llm_client import LLMClient, CircuitBreaker


class Config:
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.0-flash")
    TEMPERATURE = float(os.getenv("TEMPERATURE", "0.3"))
    MAX_TOKENS = int(os.getenv("MAX_TOKENS", "1024"))


class InventoryItem(BaseModel):
    product_id: str
    name: str
    current_stock: int
    daily_sales: float
    lead_time_days: int
    supplier_moq: int = 1
    storage_cost_per_day: float = 0.50
    unit_cost: float = 0
    unit_price: float = 0
    category: str = "general"
    last_restock_date: Optional[str] = None
    supplier_reliability: float = 0.95
    reorder_point: Optional[int] = None
    safety_stock: Optional[int] = None
    warehouse_capacity: Optional[int] = None
    on_order: int = 0
    backordered: int = 0


class InventoryAnalysis(BaseModel):
    product_id: str
    product_name: str
    current_stock: int
    recommended_action: str
    reorder_quantity: int
    urgency: str
    days_of_stock_remaining: float
    stockout_risk_days: int
    demand_forecast_30d: int
    demand_forecast_60d: int
    demand_forecast_90d: int
    cost_impact: float
    reasoning: str
    seasonal_alert: Optional[str] = None
    supplier_recommendation: Optional[str] = None


class BulkAnalysisRequest(BaseModel):
    items: List[InventoryItem]


class BulkAnalysisResponse(BaseModel):
    results: List[InventoryAnalysis]
    summary: Dict[str, Any]


SYSTEM_PROMPT = """You are an expert Inventory Management AI for ecommerce businesses.

YOUR ROLE:
- Analyze inventory levels and make data-driven recommendations
- Forecast demand using historical patterns
- Optimize reorder quantities to minimize costs
- Prevent stockouts while avoiding overstock

DECISION FRAMEWORK:
1. MAINTAIN - Stock levels are optimal (30-60 days of stock)
2. REORDER - Need to place purchase order (<30 days of stock)
3. CLEARANCE - Overstocked, run promotions (>90 days of stock)
4. DISCONTINUE - Product not selling, liquidate

ANALYSIS FACTORS:
- Current stock vs historical sales velocity
- Lead time from suppliers (including variability)
- Seasonal demand patterns
- Product lifecycle stage
- Storage costs vs stockout costs
- Supplier reliability scores
- Economies of scale in ordering
- Minimum Order Quantities (MOQ)
- Warehouse capacity constraints
- Safety stock requirements

FORMULA REFERENCE:
- Days of Stock = current_stock / max(daily_sales, 0.1)
- Reorder Point = daily_sales * lead_time_days * 1.5
- Safety Stock = daily_sales * lead_time_days * 0.5

OUTPUT FORMAT (JSON):
{
    "recommended_action": "maintain",
    "reorder_quantity": 0,
    "urgency": "low",
    "days_of_stock_remaining": 45,
    "stockout_risk_days": 25,
    "demand_forecast_30d": 200,
    "demand_forecast_60d": 420,
    "demand_forecast_90d": 650,
    "cost_impact": 1250.00,
    "reasoning": "Detailed explanation of your analysis",
    "seasonal_alert": null,
    "supplier_recommendation": "Consider negotiating bulk discount"
}

IMPORTANT RULES:
- Never recommend actions that cause stockouts on high-velocity items
- Consider carrying costs vs stockout costs (stockout cost = 3x daily profit)
- Account for supplier minimum order quantities
- Factor in warehouse capacity constraints
- Consider bundling and cross-selling opportunities
- Flag items approaching expiry or end-of-life
"""


class InventoryAgent:
    """AI Inventory Management Agent"""

    def __init__(self):
        self.config = Config()
        self.llm = LLMClient(
            system_prompt=SYSTEM_PROMPT,
            temperature=self.config.TEMPERATURE,
            max_tokens=self.config.MAX_TOKENS,
            circuit_breaker=CircuitBreaker(threshold=5, recovery_timeout=60),
        )

    async def close(self):
        await self.llm.close()

    async def analyze(self, item: InventoryItem) -> InventoryAnalysis:
        days_of_stock = item.current_stock / max(item.daily_sales, 0.1)
        reorder_point = item.daily_sales * item.lead_time_days * 1.5
        safety_stock = item.daily_sales * item.lead_time_days * 0.5

        context = f"""
Analyze inventory for this product:

Product ID: {item.product_id}
Product Name: {item.name}
Category: {item.category}
Current Stock: {item.current_stock} units
Daily Sales (avg): {item.daily_sales:.1f} units/day
Days of Stock: {days_of_stock:.0f} days
Lead Time: {item.lead_time_days} days
Supplier MOQ: {item.supplier_moq} units
Reorder Point: {reorder_point:.0f} units
Safety Stock: {safety_stock:.0f} units
Storage Cost/Day: ${item.storage_cost_per_day:.2f}
Unit Cost: ${item.unit_cost:.2f}
Unit Price: ${item.unit_price:.2f}
Supplier Reliability: {item.supplier_reliability:.0%}
On Order: {item.on_order} units
Backordered: {item.backordered} units
Last Restock: {item.last_restock_date or 'Unknown'}

Current status suggests: stockout in {days_of_stock:.0f} days at current rate.

Provide your analysis as JSON.
"""
        try:
            result = await self.llm.call(context)
            data = json.loads(result.text) if result.text else {}

            return InventoryAnalysis(
                product_id=item.product_id,
                product_name=item.name,
                current_stock=item.current_stock,
                recommended_action=data.get("recommended_action", "maintain"),
                reorder_quantity=data.get("reorder_quantity", 0),
                urgency=data.get("urgency", "low"),
                days_of_stock_remaining=round(days_of_stock, 1),
                stockout_risk_days=data.get("stockout_risk_days", int(days_of_stock * 0.7)),
                demand_forecast_30d=data.get("demand_forecast_30d", int(item.daily_sales * 30)),
                demand_forecast_60d=data.get("demand_forecast_60d", int(item.daily_sales * 60)),
                demand_forecast_90d=data.get("demand_forecast_90d", int(item.daily_sales * 90)),
                cost_impact=float(data.get("cost_impact", 0)),
                reasoning=data.get("reasoning", "Analysis completed"),
                seasonal_alert=data.get("seasonal_alert"),
                supplier_recommendation=data.get("supplier_recommendation"),
            )
        except Exception:
            return self._rule_based_fallback(item)

    async def analyze_bulk(self, items: List[InventoryItem]) -> BulkAnalysisResponse:
        results = []
        critical_count = 0
        high_count = 0
        total_cost_impact = 0.0

        for item in items:
            result = await self.analyze(item)
            results.append(result)

            if result.urgency == "critical":
                critical_count += 1
            elif result.urgency == "high":
                high_count += 1
            total_cost_impact += result.cost_impact

        return BulkAnalysisResponse(
            results=results,
            summary={
                "total_items": len(items),
                "critical_items": critical_count,
                "high_urgency": high_count,
                "items_needing_reorder": sum(1 for r in results if r.recommended_action == "reorder"),
                "items_on_clearance": sum(1 for r in results if r.recommended_action == "clearance"),
                "items_to_discontinue": sum(1 for r in results if r.recommended_action == "discontinue"),
                "total_cost_impact": round(total_cost_impact, 2),
                "total_reorder_quantity": sum(r.reorder_quantity for r in results),
                "analysis_time": datetime.now().isoformat(),
            },
        )

    async def forecast_demand(self, item: InventoryItem) -> Dict:
        context = f"""
Forecast demand for this product:

Product ID: {item.product_id}
Product Name: {item.name}
Category: {item.category}
Daily Sales (avg): {item.daily_sales:.1f} units/day
Lead Time: {item.lead_time_days} days

Provide:
- next_30_days: Expected sales for next 30 days
- next_60_days: Expected sales for next 60 days
- next_90_days: Expected sales for next 90 days
- peak_season: Month with highest demand
- low_season: Month with lowest demand
- confidence: Confidence level (0.0-1.0)
"""
        try:
            result = await self.llm.call(context)
            return json.loads(result.text) if result.text else {}
        except Exception:
            return {
                "next_30_days": int(item.daily_sales * 30),
                "next_60_days": int(item.daily_sales * 60),
                "next_90_days": int(item.daily_sales * 90),
                "peak_season": "december",
                "low_season": "february",
                "confidence": 0.7,
            }

    def _rule_based_fallback(self, item: InventoryItem) -> InventoryAnalysis:
        days_of_stock = item.current_stock / max(item.daily_sales, 0.1)
        reorder_point = item.daily_sales * item.lead_time_days * 1.5
        safety_stock = item.daily_sales * item.lead_time_days * 0.5

        if days_of_stock < item.lead_time_days:
            urgency = "critical"
            action = "reorder"
            reorder_qty = int(item.daily_sales * 60 - item.current_stock + item.on_order)
            reasoning = f"CRITICAL: Only {days_of_stock:.0f} days of stock left. Lead time is {item.lead_time_days} days. Immediate reorder needed."
        elif days_of_stock < item.lead_time_days * 2:
            urgency = "high"
            action = "reorder"
            reorder_qty = int(item.daily_sales * 30)
            reasoning = f"HIGH: {days_of_stock:.0f} days of stock remaining. Reorder soon to prevent stockout."
        elif days_of_stock > 90:
            urgency = "medium"
            action = "clearance"
            reorder_qty = 0
            reasoning = f"OVERSTOCKED: {days_of_stock:.0f} days of stock. Consider promotions to reduce inventory."
        elif days_of_stock > 180:
            urgency = "high"
            action = "discontinue"
            reorder_qty = 0
            reasoning = f"EXCESS STOCK: {days_of_stock:.0f} days of stock. Consider liquidation."
        else:
            urgency = "low"
            action = "maintain"
            reorder_qty = 0
            reasoning = f"OPTIMAL: {days_of_stock:.0f} days of stock. No action needed."

        return InventoryAnalysis(
            product_id=item.product_id,
            product_name=item.name,
            current_stock=item.current_stock,
            recommended_action=action,
            reorder_quantity=max(0, reorder_qty),
            urgency=urgency,
            days_of_stock_remaining=round(days_of_stock, 1),
            stockout_risk_days=max(0, int(days_of_stock - item.lead_time_days)),
            demand_forecast_30d=int(item.daily_sales * 30),
            demand_forecast_60d=int(item.daily_sales * 60),
            demand_forecast_90d=int(item.daily_sales * 90),
            cost_impact=round(item.unit_cost * reorder_qty * 0.15, 2),
            reasoning=reasoning,
            seasonal_alert="Monitor seasonal demand patterns" if item.daily_sales > 10 else None,
            supplier_recommendation=None,
        )


agent = InventoryAgent()
