import React from "react";

interface ConfirmationDialogProps {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}

const ConfirmationDialog: React.FC<ConfirmationDialogProps> = ({
  title,
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  onConfirm,
  onCancel,
}) => (
  <div className="confirmation-dialog">
    <h3>{title}</h3>
    <p>{message}</p>
    <div className="actions">
      <button onClick={onCancel}>{cancelLabel}</button>
      <button className="danger" onClick={onConfirm}>
        {confirmLabel}
      </button>
    </div>
  </div>
);

export default ConfirmationDialog;
