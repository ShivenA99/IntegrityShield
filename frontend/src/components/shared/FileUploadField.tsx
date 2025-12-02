import React, { useRef } from "react";
import { View } from "@instructure/ui-view";
import { Flex } from "@instructure/ui-flex";
import { Text } from "@instructure/ui-text";
import { Button } from "@instructure/ui-buttons";
import { FileDrop } from "@instructure/ui-file-drop";
import { IconUploadLine, IconDocumentLine } from "@instructure/ui-icons";

interface FileUploadFieldProps {
  label: string;
  description?: string;
  accept?: string;
  file: File | null;
  onFileSelect: (file: File | null) => void;
  disabled?: boolean;
  required?: boolean;
}

/**
 * FileUploadField - Accessible file upload with drag-and-drop
 *
 * Features:
 * - InstUI FileDrop for drag-and-drop
 * - Click to browse alternative
 * - File preview with clear option
 * - Accessible labels and instructions
 */
export const FileUploadField: React.FC<FileUploadFieldProps> = ({
  label,
  description,
  accept = "*",
  file,
  onFileSelect,
  disabled = false,
  required = false,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDrop = (acceptedFiles: File[]) => {
    if (acceptedFiles.length > 0) {
      onFileSelect(acceptedFiles[0]);
    }
  };

  const handleBrowse = () => {
    fileInputRef.current?.click();
  };

  const handleFileInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = event.target.files?.[0] || null;
    onFileSelect(selectedFile);
  };

  const handleClear = () => {
    onFileSelect(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  return (
    <View as="div">
      <View as="label" margin="0 0 xx-small" display="block">
        <Text weight="normal" size="small">
          {label}
          {required && (
            <Text color="danger" weight="normal">
              {" "}
              *
            </Text>
          )}
        </Text>
      </View>
      {description && (
        <View as="div" margin="0 0 x-small">
          <Text size="x-small" color="secondary">
            {description}
          </Text>
        </View>
      )}

      {!file ? (
        <FileDrop
          accept={accept}
          onDropAccepted={handleDrop}
          onDropRejected={() => {}}
          shouldAllowMultiple={false}
          interaction={disabled ? "disabled" : "enabled"}
          renderLabel={
            <View as="div" padding="medium" textAlign="center">
              <Flex direction="column" alignItems="center" gap="x-small">
                <IconUploadLine size="medium" />
                <Text size="small" weight="normal">Click to browse or drag file here</Text>
              </Flex>
            </View>
          }
        />
      ) : (
        <View
          as="div"
          background="secondary"
          padding="x-small small"
          borderRadius="small"
          borderWidth="small"
        >
          <Flex alignItems="center" justifyItems="space-between">
            <Flex alignItems="center" gap="small">
              <IconDocumentLine size="x-small" />
              <div>
                <Text weight="normal" size="small">{file.name}</Text>
                <br />
                <Text size="x-small" color="secondary">
                  {(file.size / 1024).toFixed(1)} KB
                </Text>
              </div>
            </Flex>
            <Button color="secondary" size="small" withBackground={false} onClick={handleClear} disabled={disabled}>
              Clear
            </Button>
          </Flex>
        </View>
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept={accept}
        onChange={handleFileInputChange}
        style={{ display: "none" }}
        aria-label={label}
      />

      {!file && (
        <View as="div" textAlign="center" margin="x-small 0 0">
          <Button
            color="secondary"
            size="small"
            withBackground={false}
            onClick={handleBrowse}
            interaction={disabled ? "disabled" : "enabled"}
          >
            Browse Files
          </Button>
        </View>
      )}
    </View>
  );
};
