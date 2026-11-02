import { Toaster as Sonner, toast } from "sonner"
import { useMode } from "@/hooks/useMode"

/** Toasts as raised copy-paper sheets; sonner's own light/dark follows the app's theme switch. */
const Toaster = ({
  ...props
}) => {
  const mode = useMode()

  return (
    <Sonner
      theme={mode === "light" ? "light" : "dark"}
      className="toaster group"
      toastOptions={{
        classNames: {
          toast:
            "group toast group-[.toaster]:rounded-none group-[.toaster]:border-0 group-[.toaster]:bg-paper-3 group-[.toaster]:text-ink group-[.toaster]:font-sans group-[.toaster]:shadow-sheet",
          description: "group-[.toast]:text-muted-foreground",
          actionButton:
            "group-[.toast]:bg-primary group-[.toast]:text-primary-foreground",
          cancelButton:
            "group-[.toast]:bg-muted group-[.toast]:text-muted-foreground",
        },
      }}
      {...props} />
  );
}

export { Toaster, toast }
