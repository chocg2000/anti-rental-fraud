export default function ScreenShell({ step, title, subtitle, toast, children, footer }) {
  return (
    <div className="relative mx-auto flex min-h-svh w-full max-w-md flex-col overflow-hidden bg-white sm:my-6 sm:min-h-0 sm:rounded-2xl sm:border sm:border-gray-200 sm:shadow-sm">
      {toast}

      <header className="shrink-0 border-b border-gray-200 px-5 pt-5 pb-4">
        {step && (
          <div className="mb-3.5 flex gap-1.5">
            {[1, 2, 3].map((n) => (
              <div key={n} className={`h-1 flex-1 rounded-full ${n <= step ? 'bg-gray-900' : 'bg-gray-200'}`} />
            ))}
          </div>
        )}
        <div className="mb-1 text-xs text-gray-500">{subtitle}</div>
        <h1 className="text-xl font-bold text-gray-900">{title}</h1>
      </header>

      <div className="flex-1 overflow-y-auto px-5 py-5">{children}</div>

      {footer && <footer className="shrink-0 border-t border-gray-200 px-5 pt-4 pb-6">{footer}</footer>}
    </div>
  )
}
