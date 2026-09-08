import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import { ScanLine, FileSearch, GitCompareArrows, DatabaseZap, ShieldCheck } from "lucide-react";

/**
 * Blocking popup shown while a real scan submission is in flight, per user
 * directive - a step-by-step animated sequence ("Analyzing", "Extracting",
 * "Matching", "Checking Tatmeen", "Validating Tatmeen") instead of a bare
 * spinner, so the wait reads as real work happening rather than a frozen
 * screen. Purely cosmetic pacing (auto-advances on a timer) - it doesn't
 * know the real request's actual progress, since the backend returns one
 * final response, not intermediate step events; per user directive it
 * loops continuously through the steps for as long as the real call is in
 * flight (never freezes on "Validating Tatmeen" just because that's the
 * last one), and closes immediately once the parent's `active` prop goes
 * false (parent unmounts/hides it once the real API call resolves).
 */
const STEPS = [
  { label: "Analyzing photo", Icon: ScanLine },
  { label: "Extracting item data", Icon: FileSearch },
  { label: "Matching against invoice", Icon: GitCompareArrows },
  { label: "Checking Tatmeen", Icon: DatabaseZap },
  { label: "Validating Tatmeen", Icon: ShieldCheck },
];
const STEP_DURATION_MS = 1600;

export default function AnalyzingModal({ active }: { active: boolean }) {
  const [stepIndex, setStepIndex] = useState(0);

  useEffect(() => {
    if (!active) {
      setStepIndex(0);
      return;
    }
    const interval = setInterval(() => {
      setStepIndex((i) => (i + 1) % STEPS.length);
    }, STEP_DURATION_MS);
    return () => clearInterval(interval);
  }, [active]);

  const current = STEPS[stepIndex];

  return createPortal(
    <AnimatePresence>
      {active && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: "rgba(10,20,18,0.72)" }}
        >
          <motion.div
            initial={{ opacity: 0, y: 12, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 8, scale: 0.96 }}
            transition={{ duration: 0.2 }}
            className="w-full max-w-sm rounded-2xl bg-white shadow-2xl overflow-hidden p-7 text-center"
          >
            <div className="relative h-16 w-16 mx-auto mb-5">
              <motion.div
                className="absolute inset-0 rounded-full"
                style={{ border: "3px solid var(--color-line)" }}
              />
              <motion.div
                className="absolute inset-0 rounded-full"
                style={{ border: "3px solid var(--color-accent)", borderRightColor: "transparent", borderTopColor: "transparent" }}
                animate={{ rotate: 360 }}
                transition={{ duration: 1.1, repeat: Infinity, ease: "linear" }}
              />
              <AnimatePresence mode="wait">
                <motion.div
                  key={stepIndex}
                  initial={{ opacity: 0, scale: 0.6 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.6 }}
                  transition={{ duration: 0.25 }}
                  className="absolute inset-0 flex items-center justify-center"
                  style={{ color: "var(--color-accent)" }}
                >
                  <current.Icon size={24} strokeWidth={2.25} />
                </motion.div>
              </AnimatePresence>
            </div>

            <AnimatePresence mode="wait">
              <motion.p
                key={stepIndex}
                initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.2 }}
                className="text-sm font-semibold"
              >
                {current.label}…
              </motion.p>
            </AnimatePresence>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body
  );
}
