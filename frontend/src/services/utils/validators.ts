export function validatePdfFile(file: File): string | null {
  if (!file.type.includes("pdf")) {
    return "Only PDF files are supported";
  }
  if (file.size > 200 * 1024 * 1024) {
    return "PDF must be under 200 MB";
  }
  return null;
}
