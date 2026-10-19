import React, { useState, useCallback, useRef } from 'react';
import '../styles/FileDrop.css';

/**
 * A drag and drop component for file uploads.
 * Files are sent to the Django database for storage via an event flowing upwards through the "onUpload" prop.
 */
const FileDrop = ({
  onUpload,
  accept = ".pdf,.csv,application/pdf,text/csv",
  maxSize = 20 * 1024 * 1024, // 20 MB matching Django limits
  multiple = true,
  className = "",
  itemType = "document"
}) => {
  const [dragActive, setDragActive] = useState(false);
  const [error, setError] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const fileInputRef = useRef(null);

  /* Drop Zone event handlers */
  const handleDrag = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  }, []);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      if (file.size > maxSize) {
         setError(`File is too large. Max size is ${maxSize / (1024 * 1024)}MB.`);
         return;
      }
      setSelectedFile(file);
      setError(null);
    }
  }, [maxSize]);

  const handleChange = (e) => {
    e.preventDefault();
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      if (file.size > maxSize) {
        setError(`File is too large. Max size is ${maxSize / (1024 * 1024)}MB.`);
        return;
      }
      setSelectedFile(file);
      setError(null);
    }
  };

  /* Send to the parent page for upload to the Django database */
  const handleUploadSubmit = async () => {
    if (!selectedFile) return;
    
    setIsUploading(true);
    setError(null);
    try {
      const success = await onUpload(selectedFile); 
      
      if (success) {
        setSelectedFile(null);
        if (fileInputRef.current) fileInputRef.current.value = "";
      } else {
        setError("Upload was cancelled or failed.");
      }
    } catch (err) {
      setError("An unexpected error occurred during upload.");
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className={`file-drop-container ${className}`}>
      <div 
        className={`drop-zone ${dragActive ? 'active' : ''}`}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
      >
        <p>Drag and drop your {itemType} here, or</p>
        <input 
          type="file" 
          ref={fileInputRef}
          accept={accept}
          onChange={handleChange}
          style={{ display: 'none' }}
          id="file-upload-input"
        />
        <button 
          type="button" 
          onClick={() => fileInputRef.current.click()}
          className="btn-browse"
        >
          Browse Files
        </button>
      </div>

      {error && <p style={{ color: 'red', marginTop: '10px' }}>{error}</p>}

      {selectedFile && (
        <div className="selected-file-preview" style={{ marginTop: '15px', padding: '10px', background: '#f3f4f6', borderRadius: '5px' }}>
          <p><strong>Selected:</strong> {selectedFile.name}</p>
          <button 
            type="button" 
            onClick={handleUploadSubmit}
            disabled={isUploading}
            style={{ marginTop: '10px', padding: '8px 16px', background: '#3b82f6', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
          >
            {isUploading ? 'Uploading...' : 'Confirm Upload'}
          </button>
          <button 
            type="button" 
            onClick={() => setSelectedFile(null)}
            disabled={isUploading}
            style={{ marginTop: '10px', marginLeft: '10px', padding: '8px 16px', background: '#ef4444', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
          >
            Cancel
          </button>
        </div>
      )}
    </div>
  );
};

export default FileDrop;