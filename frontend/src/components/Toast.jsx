import { IconXCircle, IconClose } from './icons'

export default function Toast({ message, onDismiss }) {
  if (!message) return null
  return (
    <div className="absolute top-3.5 left-3.5 right-3.5 z-10 flex items-start gap-2.5 rounded-xl bg-gray-900 px-3.5 py-3 shadow-lg">
      <IconXCircle size={16} className="mt-0.5 shrink-0 text-red-400" />
      <div className="flex-1 text-[12.5px] leading-relaxed text-white">{message}</div>
      <button onClick={onDismiss} className="shrink-0 p-0.5 text-gray-400 hover:text-white">
        <IconClose />
      </button>
    </div>
  )
}
