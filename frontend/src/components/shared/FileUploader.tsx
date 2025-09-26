import React from "react";

interface FileUploaderProps {
  onFileSelected: (file: File) => void;
  disabled?: boolean;
}

const FileUploader: React.FC<FileUploaderProps> = ({ onFileSelected, disabled }) => (
  <label className="file-uploader">
    <input
      type="file"
      accept="application/pdf"
      disabled={disabled}
      onChange={(event) => {
        const file = event.target.files?.[0];
        if (file) onFileSelected(file);
      }}
    />
    <span>Drag & drop or click to upload PDF</span>
  </label>
);

export default FileUploader;
