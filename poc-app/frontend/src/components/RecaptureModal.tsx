import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import { AlertTriangle, Camera, X } from "lucide-react";

/**
 * Shown instead of navigating anywhere / instead of adding anything to the
 * results table, whenever a scan submission comes back with zero results
 * or with items that don't belong to this invoice (real_extraction's
 * "disorganized photo" / "wrong item photo" / "no barcode decoded"
 * rejections in scans.py's /upload-real, or the frontend's own unmatched-
 * items check) - per user directive: stay on the current screen, show the
 * actual photo that failed so anyone can see why, and offer a deliberate
 * "Re-capture" action. The close (X) button does the exact same thing as
 * Re-capture - there's no dismiss-without-fixing path, since a stale
 * rejected photo left in the scanner would just fail the same way again.
 */
export default function RecaptureModal({
  open, message, imagePreview, onRecapture,
}: {
  open: boolean;
  message: string;
  imagePreview: string | null;
  onRecapture: () => void;
}) {
  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: "rgba(10,20,18,0.6)" }}
        >
          <motion.div
            initial={{ opacity: 0, y: 12, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 8, scale: 0.97 }}
            transition={{ duration: 0.18 }}
            className="w-full max-w-lg rounded-2xl bg-white shadow-2xl overflow-hidden"
          >
            {imagePreview && (
              <div className="relative" style={{ background: "#0a1615" }}>
                <img
                  src={imagePreview}
                  alt="Uploaded photo that could not be analyzed"
                  className="w-full h-72 object-contain"
                />
                <div
                  className="absolute inset-x-0 bottom-0 h-16 pointer-events-none"
                  style={{ background: "linear-gradient(to top, rgba(0,0,0,0.65), transparent)" }}
                />
                <div
                  className="absolute bottom-3 left-3.5 inline-flex items-center gap-1.5 text-[11px] font-semibold text-white px-2.5 py-1 rounded-full"
                  style={{ background: "rgba(220,38,38,0.92)" }}
                >
                  <AlertTriangle size={12} strokeWidth={2.5} />
                  Could not analyze this photo
                </div>
                <button
                  onClick={onRecapture}
                  aria-label="Close"
                  className="absolute top-3 right-3 h-8 w-8 rounded-full flex items-center justify-center text-white transition-colors hover:bg-white/20"
                  style={{ background: "rgba(0,0,0,0.45)" }}
                >
                  <X size={16} strokeWidth={2.5} />
                </button>
              </div>
            )}
            <div className="p-6">
              <div className="flex items-start gap-3 mb-4">
                <div
                  className="h-10 w-10 rounded-full flex items-center justify-center shrink-0"
                  style={{ background: "var(--color-red-tint)" }}
                >
                  <AlertTriangle size={19} style={{ color: "var(--color-red)" }} strokeWidth={2.25} />
                </div>
                <div className="pt-0.5">
                  <h3 className="text-base font-bold leading-snug">Please rearrange and retake the photo</h3>
                  <p className="text-sm text-[var(--color-muted)] mt-1 leading-relaxed">{message}</p>
                </div>
              </div>
              <motion.button
                whileHover={{ scale: 1.01 }}
                whileTap={{ scale: 0.99 }}
                onClick={onRecapture}
                className="w-full rounded-lg px-4 py-3 text-sm font-semibold text-white flex items-center justify-center gap-2"
                style={{ background: "linear-gradient(135deg, var(--color-accent), #0a5e6d)" }}
              >
                <Camera size={15} strokeWidth={2.5} />
                Re-capture Photo
              </motion.button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body
  );
}
