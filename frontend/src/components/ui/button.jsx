import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva } from "class-variance-authority";

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  // Focus uses the global 2px outline from base.css. Disabled shows three cues: opacity,
  // the not-allowed cursor and the native attribute (gate 39a). Paper physics: a button on a
  // hard ink offset drops 1px into it on hover and all the way in on press.
  "inline-flex items-center justify-center gap-2 whitespace-nowrap text-[15px] font-medium transition-[background-color,color,transform,box-shadow] duration-micro ease-out disabled:cursor-not-allowed disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "bg-signal text-signal-ink shadow-offset disabled:bg-paper-3 disabled:text-ink-3 disabled:opacity-100 hover:translate-x-px hover:translate-y-px hover:shadow-offset-sm active:translate-x-1 active:translate-y-1 active:shadow-none disabled:translate-x-0 disabled:translate-y-0 disabled:shadow-offset",
        destructive:
          "bg-error text-error-ink shadow-offset hover:translate-x-px hover:translate-y-px hover:shadow-offset-sm active:translate-x-1 active:translate-y-1 active:shadow-none disabled:translate-x-0 disabled:translate-y-0 disabled:shadow-offset",
        outline:
          "bg-paper-3 text-ink shadow-offset hover:translate-x-px hover:translate-y-px hover:shadow-offset-sm active:translate-x-1 active:translate-y-1 active:shadow-none disabled:translate-x-0 disabled:translate-y-0 disabled:shadow-offset",
        secondary:
          "bg-paper-3 text-ink shadow-card hover:bg-hover",
        ghost: "text-ink hover:bg-paper-3 hover:shadow-card",
        link: "text-ink underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 px-4",
        sm: "h-8 px-3",
        lg: "h-12 px-6 text-base",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

const Button = React.forwardRef(({ className, variant, size, asChild = false, ...props }, ref) => {
  const Comp = asChild ? Slot : "button"
  return (
    <Comp
      className={cn(buttonVariants({ variant, size, className }))}
      ref={ref}
      {...props} />
  );
})
Button.displayName = "Button"

export { Button, buttonVariants }
