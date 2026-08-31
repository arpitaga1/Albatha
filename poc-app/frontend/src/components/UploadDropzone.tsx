import { useRef, useState, type DragEvent } from "react";
import { motion } from "framer-motion";

interface Props {
  label: string;
  hint: string;
  onFile: (file: File) => void;
  preview: string | null; // object URL, if an image was chosen
  fileName: string | null;
  // When this dropzone is the lower half of a merged hero card (see
  // StartValidationPage), it has no top border/radius or shadow of its
  // own — the parent wrapper owns the unified card shell, and this only
  // supplies the inner dashed drop-target so the "drop here" affordance
  // still reads clearly against the header above it.
  embedded?: boolean;
}

export default function UploadDropzone({ label, hint, onFile, preview, fileName, embedded = false }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  function handleDrop(e: DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) onFile(file);
  }

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
      className={
        embedded
          ? "border-t-2 border-dashed cursor-pointer transition-colors flex flex-col items-center justify-center text-center p-8 min-h-[220px]"
          : "rounded-xl border-2 border-dashed cursor-pointer transition-colors flex flex-col items-center justify-center text-center p-8 min-h-[280px]"
      }
      style={{
        borderColor: dragOver ? "var(--color-accent)" : "var(--color-line)",
        background: dragOver ? "var(--color-accent-tint, #e2efef)" : "white",
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept="image/*,application/pdf"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFile(file);
        }}
      />
      {preview ? (
        <motion.img
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          src={preview}
          alt={fileName ?? "preview"}
          className="max-h-56 rounded-lg shadow-sm object-contain"
        />
      ) : fileName ? (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col items-center gap-2">
          <div className="h-14 w-14 rounded-xl flex items-center justify-center text-2xl" style={{ background: "var(--color-line)" }}>
            📄
          </div>
          <div className="text-sm font-medium">{fileName}</div>
        </motion.div>
      ) : (
        <>
          <div className="h-12 w-12 rounded-xl flex items-center justify-center text-xl mb-3"
               style={{ background: "var(--color-accent-tint, #e2efef)", color: "var(--color-accent)" }}>
            ⬆
          </div>
          <div className="font-medium text-sm">{label}</div>
          <div className="text-xs text-[var(--color-muted)] mt-1 max-w-[220px]">{hint}</div>
        </>
      )}
    </div>
  );
}
