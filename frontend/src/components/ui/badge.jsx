import * as React from "react"
import { cva } from "class-variance-authority";

import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center border px-2 py-0.5 text-xs font-medium",
  {
    variants: {
      variant: {
        default:
          "border-ink bg-paper-3 text-ink",
        secondary:
          "border-transparent bg-paper-2 text-ink-2",
        destructive:
          "border-transparent bg-error text-error-ink",
        outline: "text-foreground",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

function Badge({
  className,
  variant,
  ...props
}) {
  return (<div className={cn(badgeVariants({ variant }), className)} {...props} />);
}

export { Badge, badgeVariants }
