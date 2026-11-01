/** @type {import('tailwindcss').Config} */
// Every colour, font and size below is a var() of a token in src/tokens.css (the Paste-up theme),
// so the light/dark switch changes the variables and every utility follows.
module.exports = {
    darkMode: ["class"],
    content: ["./src/**/*.{js,jsx,ts,tsx}", "./public/index.html"],
    theme: {
        // Paste-up: paper is cut square. Replacing (not extending) the scale makes every
        // rounded-* utility, including the ones inside ui/ components, resolve to square.
        borderRadius: {
            none: "0",
            sm: "0",
            DEFAULT: "0",
            md: "0",
            lg: "0",
            xl: "0",
            "2xl": "0",
            "3xl": "0",
            full: "0",
        },
        // Paste-up: paper lifts (card, sheet) and hard ink offsets under controls (offset,
        // offset-sm for the hover drop). The stock shadcn names map onto the paper lifts.
        boxShadow: {
            none: "none",
            sm: "var(--shadow-card)",
            DEFAULT: "var(--shadow-card)",
            md: "var(--shadow-card)",
            lg: "var(--shadow-sheet)",
            xl: "var(--shadow-sheet)",
            card: "var(--shadow-card)",
            sheet: "var(--shadow-sheet)",
            offset: "4px 4px 0 var(--color-offset)",
            "offset-sm": "3px 3px 0 var(--color-offset)",
            "offset-xs": "2px 2px 0 var(--color-offset)",
        },
        extend: {
            fontFamily: {
                sans: ["var(--font-body)"],
                display: ["var(--font-display)"],
            },
            fontSize: {
                display: ["var(--text-display)", { lineHeight: "1.02" }],
                "display-s": ["var(--text-display-s)", { lineHeight: "1.02" }],
                section: ["var(--text-section)", { lineHeight: "1.05" }],
                title: ["var(--text-title)", { lineHeight: "1.2" }],
                lead: ["var(--text-lead)", { lineHeight: "1.45" }],
            },
            colors: {
                // Hallmark roles. accent and muted are renamed signal (the fluorescent) and ink-3 here, because
                // shadcn already uses those two names for other things (export-formats.md).
                paper: {
                    DEFAULT: "var(--color-paper)",
                    2: "var(--color-paper-2)",
                    3: "var(--color-paper-3)",
                },
                ink: {
                    DEFAULT: "var(--color-ink)",
                    2: "var(--color-ink-2)",
                    3: "var(--color-muted)",
                },
                rule: {
                    DEFAULT: "var(--color-rule)",
                    2: "var(--color-rule-2)",
                },
                signal: {
                    DEFAULT: "var(--color-accent)",
                    ink: "var(--color-accent-ink)",
                    hover: "var(--color-accent-hover)",
                    2: "var(--color-accent-2)",
                },
                own: "var(--color-own)",
                offset: "var(--color-offset)",
                // Coloured copy paper for rooms and people (lib/format.js paperFor).
                room: {
                    1: "var(--color-room-1)",
                    2: "var(--color-room-2)",
                    3: "var(--color-room-3)",
                    4: "var(--color-room-4)",
                    5: "var(--color-room-5)",
                    6: "var(--color-room-6)",
                    ink: "var(--color-room-ink)",
                },
                hover: "var(--color-hover)",
                overlay: "var(--color-overlay)",
                focus: "var(--color-focus)",
                error: {
                    DEFAULT: "var(--color-error)",
                    ink: "var(--color-error-ink)",
                },
                success: "var(--color-success)",
                // shadcn names, mapped in src/index.css onto the tokens above.
                background: "var(--background)",
                foreground: "var(--foreground)",
                card: {
                    DEFAULT: "var(--card)",
                    foreground: "var(--card-foreground)",
                },
                popover: {
                    DEFAULT: "var(--popover)",
                    foreground: "var(--popover-foreground)",
                },
                primary: {
                    DEFAULT: "var(--primary)",
                    foreground: "var(--primary-foreground)",
                },
                secondary: {
                    DEFAULT: "var(--secondary)",
                    foreground: "var(--secondary-foreground)",
                },
                muted: {
                    DEFAULT: "var(--muted)",
                    foreground: "var(--muted-foreground)",
                },
                accent: {
                    DEFAULT: "var(--accent)",
                    foreground: "var(--accent-foreground)",
                },
                destructive: {
                    DEFAULT: "var(--destructive)",
                    foreground: "var(--destructive-foreground)",
                },
                border: "var(--border)",
                input: "var(--input)",
                ring: "var(--ring)",
            },
            transitionDuration: {
                micro: "var(--dur-micro)",
                short: "var(--dur-short)",
            },
            transitionTimingFunction: {
                out: "var(--ease-out)",
            },
            keyframes: {
                "accordion-down": {
                    from: { height: "0" },
                    to: { height: "var(--radix-accordion-content-height)" },
                },
                "accordion-up": {
                    from: { height: "var(--radix-accordion-content-height)" },
                    to: { height: "0" },
                },
            },
            animation: {
                "accordion-down": "accordion-down 0.2s ease-out",
                "accordion-up": "accordion-up 0.2s ease-out",
            },
        },
    },
    plugins: [require("tailwindcss-animate")],
};
