type Listener = (msg: string) => void

let listeners: Listener[] = []

export function showToast(msg: string) {
  listeners.forEach(l => l(msg))
}

export function onToast(cb: Listener) {
  listeners.push(cb)
  return () => { listeners = listeners.filter(l => l !== cb) }
}
