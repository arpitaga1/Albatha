import { useEffect, useRef, useState, type DragEvent, type ReactNode } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { AlertTriangle, Camera, Upload, X } from "lucide-react";

type CameraState = "idle" | "requesting" | "live" | "denied" | "unavailable" | "unsupported";

/**
 * Modern mobile/payment-scanner-style capture UI, per the spec's Step 4:
 * "The experience should feel similar to a modern mobile/payment scanner
 * interface, with: Camera/scanner area, Scanning frame, Instructions, Scan
 * status, Captured item information, Option to upload an image."
 *
 * Uses the real laptop/device camera (getUserMedia) as the primary capture
 * mechanism — per user request, this is now an actual live scanner, not a
 * dressed-up file dropzone. "Capture Photo" grabs the current video frame
 * and feeds it into the exact same onAddFiles pipeline a dropped/browsed
 * file would use, so nothing downstream (multi-photo batching, barcode
 * decode) needs to know which path a photo came from. File upload is kept
 * as an explicit fallback — camera permission can be denied, no camera may
 * be present, or a user may simply want to reuse an existing photo (e.g.
 * the project's own fixture images) — never removed, just no longer the
 * only option.
 *
 * The video is intentionally NOT mirrored — a mirrored feed would flip any
 * barcode/text in the captured frame and break decoding, unlike a typical
 * "selfie" camera UI where mirroring is expected.
 */
export default function ScannerFrame({
  files, previews, onAddFiles, onRemoveFile, status, statusVariant = "idle", children,
}: {
  files: File[];
  previews: string[];
  onAddFiles: (files: File[]) => void;
  onRemoveFile: (index: number) => void;
  status: string;
  statusVariant?: "idle" | "active" | "success" | "error";
  children?: ReactNode;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [cameraState, setCameraState] = useState<CameraState>(
    typeof navigator !== "undefined" && navigator.mediaDevices ? "idle" : "unsupported"
  );
  const [flash, setFlash] = useState(false);

  useEffect(() => {
    if (cameraState === "live" && videoRef.current && streamRef.current) {
      videoRef.current.srcObject = streamRef.current;
    }
  }, [cameraState]);

  function classifyError(err: unknown): CameraState {
    const name = err instanceof DOMException ? err.name : "";
    return name === "NotFoundError" || name === "OverconstrainedError" ? "unavailable" : "denied";
  }

  function requestCamera() {
    return navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1080 } },
      audio: false,
    });
  }

  // Open the camera the moment this screen is reached — per user request,
  // no extra click needed. Guarded with a `cancelled` flag rather than a
  // bare fire-and-forget call: React 18 StrictMode runs effects twice in
  // dev (mount -> cleanup -> mount), and without this guard that would
  // race two concurrent getUserMedia calls and leak whichever stream lost
  // the race (camera light staying on with no visible feed using it).
  useEffect(() => {
    if (cameraState !== "idle") return;
    let cancelled = false;
    setCameraState("requesting");
    requestCamera()
      .then((stream) => {
        if (cancelled) { stream.getTracks().forEach((t) => t.stop()); return; }
        streamRef.current = stream;
        setCameraState("live");
      })
      .catch((err) => {
        if (!cancelled) setCameraState(classifyError(err));
      });
    return () => {
      cancelled = true;
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    };
  }, []);

  async function startCamera() {
    setCameraState("requesting");
    try {
      const stream = await requestCamera();
      streamRef.current = stream;
      setCameraState("live");
    } catch (err) {
      setCameraState(classifyError(err));
    }
  }

  function stopCamera() {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setCameraState("idle");
  }

  function capturePhoto() {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || video.videoWidth === 0) return;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    setFlash(true);
    setTimeout(() => setFlash(false), 180);
    canvas.toBlob((blob) => {
      if (!blob) return;
      onAddFiles([new File([blob], `capture-${Date.now()}.jpg`, { type: "image/jpeg" })]);
    }, "image/jpeg", 0.92);
  }

  function handleDrop(e: DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const dropped = Array.from(e.dataTransfer.files ?? []);
    if (dropped.length) onAddFiles(dropped);
  }

  const statusColor = {
    idle: "#8fbdb9",
    active: "#5eead4",
    success: "#6fbe93",
    error: "#ff8a80",
  }[statusVariant];

  const live = cameraState === "live";

  return (
    <div className="rounded-2xl overflow-hidden" style={{ background: "linear-gradient(160deg, #0a1615 0%, #0d2523 60%, #0b3a3d 100%)" }}>
      <canvas ref={canvasRef} className="hidden" />

      {/* Viewfinder area */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => cameraState === "idle" && startCamera()}
        className="relative h-72 flex items-center justify-center overflow-hidden"
        style={{ cursor: cameraState === "idle" ? "pointer" : "default" }}
      >
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          multiple
          className="hidden"
          onChange={(e) => {
            const picked = Array.from(e.target.files ?? []);
            if (picked.length) onAddFiles(picked);
            e.target.value = ""; // allow re-selecting the same file again later
          }}
        />

        {live && (
          <video ref={videoRef} autoPlay playsInline muted className="absolute inset-0 w-full h-full object-cover" />
        )}

        {/* Subtle grid backdrop, matches the login screen's "systems" texture */}
        <div className="absolute inset-0 opacity-[0.08] pointer-events-none"
             style={{ backgroundImage: "linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg, #fff 1px, transparent 1px)", backgroundSize: "28px 28px" }} />

        {!live && (
          <div className="relative z-10 text-center px-6">
            {cameraState === "requesting" && (
              <>
                <motion.div
                  className="mx-auto mb-3 h-6 w-6 rounded-full border-2 border-t-transparent"
                  style={{ borderColor: "#5eead4", borderTopColor: "transparent" }}
                  animate={{ rotate: 360 }} transition={{ duration: 0.8, repeat: Infinity, ease: "linear" }}
                />
                <p className="text-white/90 text-sm font-medium">Requesting camera access…</p>
              </>
            )}
            {cameraState === "idle" && (
              <>
                <p className="text-white/90 text-sm font-medium mb-3">Position the item in the frame</p>
                <button
                  onClick={(e) => { e.stopPropagation(); startCamera(); }}
                  className="inline-flex items-center gap-2 text-sm font-semibold px-4 py-2 rounded-full text-white"
                  style={{ background: "var(--color-accent)" }}
                >
                  <Camera size={14} strokeWidth={2.5} /> Start Camera
                </button>
              </>
            )}
            {(cameraState === "denied" || cameraState === "unavailable" || cameraState === "unsupported") && (
              <>
                <AlertTriangle size={20} className="mx-auto mb-2" style={{ color: "#ff8a80" }} />
                <p className="text-white/90 text-sm font-medium mb-1">
                  {cameraState === "denied" && "Camera access denied"}
                  {cameraState === "unavailable" && "No camera found on this device"}
                  {cameraState === "unsupported" && "Camera not supported in this browser"}
                </p>
                <p className="text-xs mb-3" style={{ color: "#8fbdb9" }}>Upload photos from your device instead, below.</p>
                {cameraState !== "unsupported" && (
                  <button
                    onClick={(e) => { e.stopPropagation(); startCamera(); }}
                    className="inline-flex items-center gap-2 text-xs font-semibold px-3 py-1.5 rounded-full text-white"
                    style={{ background: "rgba(255,255,255,0.15)" }}
                  >
                    <Camera size={12} strokeWidth={2.5} /> Try Again
                  </button>
                )}
              </>
            )}
          </div>
        )}

        {/* Scanning frame corners */}
        <div className="absolute inset-8 pointer-events-none">
          {[
            { top: 0, left: 0, borderTop: "2px solid #5eead4", borderLeft: "2px solid #5eead4" },
            { top: 0, right: 0, borderTop: "2px solid #5eead4", borderRight: "2px solid #5eead4" },
            { bottom: 0, left: 0, borderBottom: "2px solid #5eead4", borderLeft: "2px solid #5eead4" },
            { bottom: 0, right: 0, borderBottom: "2px solid #5eead4", borderRight: "2px solid #5eead4" },
          ].map((corner, i) => (
            <div key={i} className="absolute h-6 w-6" style={corner} />
          ))}
        </div>

        {/* Animated scan line - ambient while idle, active "scanning" feel over a live feed */}
        <motion.div
          className="absolute left-8 right-8 h-px pointer-events-none"
          style={{ background: "linear-gradient(90deg, transparent, #5eead4, transparent)", boxShadow: "0 0 8px 1px #5eead4" }}
          animate={{ top: ["18%", "82%", "18%"] }}
          transition={{ duration: 2.6, repeat: Infinity, ease: "easeInOut" }}
        />

        {live && (
          <>
            <button
              onClick={(e) => { e.stopPropagation(); stopCamera(); }}
              className="absolute top-3 right-3 z-20 h-7 w-7 rounded-full flex items-center justify-center text-white"
              style={{ background: "rgba(0,0,0,0.55)" }}
              title="Stop camera"
            >
              <X size={14} strokeWidth={2.5} />
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); capturePhoto(); }}
              className="absolute bottom-4 left-1/2 -translate-x-1/2 z-20 h-14 w-14 rounded-full flex items-center justify-center"
              style={{ background: "rgba(255,255,255,0.95)", boxShadow: "0 0 0 3px rgba(255,255,255,0.35)" }}
              title="Capture photo"
            >
              <div className="h-11 w-11 rounded-full" style={{ background: "white", border: "2px solid #0a1615" }} />
            </button>
            <AnimatePresence>
              {flash && (
                <motion.div
                  initial={{ opacity: 0.85 }} animate={{ opacity: 0 }} exit={{ opacity: 0 }}
                  className="absolute inset-0 bg-white pointer-events-none z-30"
                />
              )}
            </AnimatePresence>
          </>
        )}

        {dragOver && <div className="absolute inset-0 bg-white/10 pointer-events-none" />}
      </div>

      {/* Captured photo thumbnails - separate strip so they never cover the live feed */}
      {files.length > 0 && (
        <div className="px-5 pt-3 flex items-center gap-2 overflow-x-auto border-t" style={{ borderColor: "rgba(255,255,255,0.08)" }}>
          {files.map((f, i) => (
            <motion.div key={`${f.name}-${i}`} initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} className="relative shrink-0">
              <img src={previews[i]} alt={f.name} className="h-14 w-14 object-cover rounded-lg" style={{ border: "1px solid rgba(255,255,255,0.15)" }} />
              <button
                onClick={() => onRemoveFile(i)}
                className="absolute -top-1.5 -right-1.5 h-5 w-5 rounded-full flex items-center justify-center text-white"
                style={{ background: "rgba(0,0,0,0.7)" }}
                title="Remove photo"
              >
                <X size={9} strokeWidth={3} />
              </button>
            </motion.div>
          ))}
        </div>
      )}

      {/* Status bar + captured info */}
      <div className="px-5 py-4 border-t" style={{ borderColor: "rgba(255,255,255,0.08)" }}>
        <div className="flex items-center justify-between gap-3 mb-1">
          <div className="flex items-center gap-2 min-w-0">
            <span className="h-1.5 w-1.5 rounded-full shrink-0" style={{ background: statusColor, boxShadow: `0 0 6px 1px ${statusColor}` }} />
            <span className="text-xs font-medium truncate" style={{ color: statusColor }}>{status}</span>
            {files.length > 0 && (
              <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full text-white/80 shrink-0" style={{ background: "rgba(255,255,255,0.1)" }}>
                {files.length} photo{files.length > 1 ? "s" : ""}
              </span>
            )}
          </div>
          <button
            onClick={() => inputRef.current?.click()}
            className="inline-flex items-center gap-1.5 text-[11px] font-semibold shrink-0"
            style={{ color: "#8fbdb9" }}
          >
            <Upload size={11} strokeWidth={2.5} /> Upload from device
          </button>
        </div>
        <AnimatePresence>
          {children && (
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} className="mt-2">
              {children}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
