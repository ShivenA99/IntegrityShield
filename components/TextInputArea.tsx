import React from 'react';

interface TextInputAreaProps {
  value: string;
  onChange: (event: React.ChangeEvent<HTMLTextAreaElement>) => void;
  placeholder?: string;
  disabled?: boolean;
}

export const TextInputArea: React.FC<TextInputAreaProps> = ({
  value,
  onChange,
  placeholder = "Enter text here...",
  disabled = false,
}) => {
  return (
    <div>
      <label htmlFor="assessmentText" className="block text-sm font-medium text-sky-300 mb-1">
        Assessment Content
      </label>
      <textarea
        id="assessmentText"
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        disabled={disabled}
        rows={8}
        className="w-full p-3 bg-slate-700 border border-slate-600 rounded-lg shadow-sm focus:ring-2 focus:ring-sky-500 focus:border-sky-500 text-slate-100 transition duration-150 disabled:opacity-60 disabled:cursor-not-allowed resize-y"
      />
       <p className="text-xs text-slate-400 mt-1">
        Enter the question or text you want the LLM to process.
      </p>
    </div>
  );
};
