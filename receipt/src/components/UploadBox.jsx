import React, { useCallback, useRef, useState } from "react";
import "../styles/UploadBox.css";

/**
 * A single labelled drag-and-drop / click-to-browse target used on the
 * centralised Uploads page. Selecting or dropping a file does not upload it
 * directly - it hands the raw File back up to the parent, which opens the
 * confirmation modal.
 */
const UploadBox = ({
  label,
  hint,
  accept = ".pdf,.csv,application/pdf,text/csv",
  onFileSelected,
}) => {
  const [dragActive, setDragActive] = useState(false);
  const inputRef = useRef(null);

  const handleDrag = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  }, []);

  const handleDrop = useCallback(
    (e) => {
      e.preventDefault();
      e.stopPropagation();
      setDragActive(false);
      const file = e.dataTransfer.files && e.dataTransfer.files[0];
      if (file) onFileSelected(file);
    },
    [onFileSelected]
  );

  const handleChange = (e) => {
    const file = e.target.files && e.target.files[0];
    if (file) onFileSelected(file);
    // Reset so selecting the same file twice in a row still fires onChange
    e.target.value = "";
  };

  return (
    <div
      className={`upload-box ${dragActive ? "upload-box-active" : ""}`}
      onDragEnter={handleDrag}
      onDragOver={handleDrag}
      onDragLeave={handleDrag}
      onDrop={handleDrop}
      onClick={() => inputRef.current.click()}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") inputRef.current.click();
      }}
    >
      <input
        type="file"
        ref={inputRef}
        accept={accept}
        onChange={handleChange}
        style={{ display: "none" }}
      />
      <span className="upload-box-label">{label}</span>
      <span className="upload-box-hint">{hint || "Drag & drop, or click to browse"}</span>
    </div>
  );
};

export default UploadBox;
