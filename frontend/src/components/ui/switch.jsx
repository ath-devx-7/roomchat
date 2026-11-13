import * as React from "react"
import * as SwitchPrimitives from "@radix-ui/react-switch"

import { cn } from "@/lib/utils"

const Switch = React.forwardRef(({ className, ...props }, ref) => (
  <SwitchPrimitives.Root
    className={cn(
      // Square track: off is an ink outline, on is the fluorescent with an ink edge.
      "peer inline-flex h-5 w-9 shrink-0 cursor-pointer items-center border border-input p-0.5 transition-colors disabled:cursor-not-allowed disabled:opacity-50 data-[state=checked]:bg-signal",
      className
    )}
    {...props}
    ref={ref}>
    <SwitchPrimitives.Thumb
      className={cn(
        "pointer-events-none block h-3.5 w-3.5 transition-transform duration-micro data-[state=checked]:translate-x-4 data-[state=checked]:bg-signal-ink data-[state=unchecked]:translate-x-0 data-[state=unchecked]:bg-ink-3"
      )} />
  </SwitchPrimitives.Root>
))
Switch.displayName = SwitchPrimitives.Root.displayName

export { Switch }
