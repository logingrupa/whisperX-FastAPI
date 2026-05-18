import {
  CircleCheckIcon,
  InfoIcon,
  Loader2Icon,
  OctagonXIcon,
  TriangleAlertIcon,
} from "lucide-react"
import { Toaster as Sonner, type ToasterProps } from "sonner"

const Toaster = ({ ...props }: ToasterProps) => {
  return (
    <Sonner
      theme="system"
      position="top-right"
      richColors
      closeButton
      expand
      visibleToasts={6}
      className="toaster group"
      toastOptions={{
        // Make sure toasts stay above ANY app-level overlay (TUS progress,
        // dialogs, the AppShell sidebar). Default sonner z-index is 9999 —
        // we bump to 2147483647 (max int) to be defensive.
        style: { zIndex: 2147483647 },
      }}
      icons={{
        success: <CircleCheckIcon className="size-4" />,
        info: <InfoIcon className="size-4" />,
        warning: <TriangleAlertIcon className="size-4" />,
        error: <OctagonXIcon className="size-4" />,
        loading: <Loader2Icon className="size-4 animate-spin" />,
      }}
      style={
        {
          "--normal-bg": "var(--popover)",
          "--normal-text": "var(--popover-foreground)",
          "--normal-border": "var(--border)",
          "--border-radius": "var(--radius)",
          zIndex: 2147483647,
        } as React.CSSProperties
      }
      {...props}
    />
  )
}

export { Toaster }
