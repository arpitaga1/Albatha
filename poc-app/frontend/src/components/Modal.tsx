import { useEffect } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import { X } from "lucide-react";

/**
 * Generic centered dialog — overlay, click-outside-to-close, Escape-to-close.
 * Introduced so item-level detail (GTIN/Batch/Expiry compare table,
 * discrepancies, Tatmeen result) moves OFF the main scan page and into a
 * popup opened per item — per client feedback: an invoice can carry up to
 * 150 line items, so rendering every item's full detail inline made the
 * page long and slow. The main table stays a fast, scannable summary; this
 * is where the detail lives now, on demand.
 */
export default function Modal({
  open, onClose, title, children, wide = false, fullScreen = false,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  wide?: boolean;
  fullScreen?: boolean;
}) {
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          className={`fixed inset-0 z-50 flex items-center justify-center ${fullScreen ? "p-0 sm:p-4" : "p-4 sm:p-8"}`}
          style={{ background: "rgba(10,20,18,0.45)" }}
          onClick={onClose}
        >
          {/*
            The header used to be `position: sticky` inside a scrolling
            overlay - but a motion.div ancestor always carries a CSS
            `transform` (even at rest, framer-motion leaves an identity
            transform in place for the scale/y entrance animation), and
            `position: sticky` simply does not work through an ancestor
            with a transform - it establishes a new containing block, so
            the header stopped sticking and scrolled with the content
            instead. Fixed by not using sticky at all: this box is a fixed-
            height flex column (`max-h-[85vh]`, `overflow-hidden`) with the
            header as a non-scrolling flex item (`shrink-0`) and the body
            as its own independently-scrolling flex item - the header
            physically can't scroll because it's outside the body's own
            overflow container, no sticky positioning involved.
          */}
          <motion.div
            initial={{ opacity: 0, y: 12, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.98 }}
            transition={{ duration: 0.18 }}
            onClick={(e) => e.stopPropagation()}
            className={
              fullScreen
                ? "w-full h-full sm:w-[96vw] sm:h-[94vh] rounded-none sm:rounded-xl bg-white shadow-2xl flex flex-col overflow-hidden"
                : `w-full ${wide ? "max-w-3xl" : "max-w-xl"} max-h-[85vh] rounded-xl bg-white shadow-2xl flex flex-col overflow-hidden`
            }
          >
            <div
              className="flex items-center justify-between px-5 py-3.5 border-b shrink-0"
              style={{ borderColor: "var(--color-line)" }}
            >
              <div className="font-semibold text-sm">{title}</div>
              <button
                onClick={onClose}
                className="rounded-md p-1 text-[var(--color-muted)] hover:bg-[var(--color-paper)] hover:text-[var(--color-ink)] transition-colors"
                aria-label="Close"
              >
                <X size={16} strokeWidth={2.25} />
              </button>
            </div>
            <div className="p-5 overflow-y-auto">{children}</div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body
  );
}
