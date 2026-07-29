import { useEffect } from 'react'
import { useSpring, useTransform, motion } from 'framer-motion'

export function AnimatedNumber({ value, suffix = '', decimals = 0 }: { value: number; suffix?: string; decimals?: number }) {
  const spring = useSpring(0, { stiffness: 90, damping: 20, mass: 0.6 })
  const display = useTransform(spring, (v) => `${v.toFixed(decimals)}${suffix}`)

  useEffect(() => {
    spring.set(value)
  }, [value])

  return <motion.span className="tabular">{display}</motion.span>
}
