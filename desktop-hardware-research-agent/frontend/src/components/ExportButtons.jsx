import React from 'react';
import { Download, FileText } from 'lucide-react';
import jsPDF from 'jspdf';

export default function ExportButtons({ markdownContent }) {
  if (!markdownContent) return null;

  const handleDownloadMarkdown = () => {
    const blob = new Blob([markdownContent], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `Hardware_Report_${Date.now()}.md`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const handleDownloadPDF = () => {
    const doc = new jsPDF({
      orientation: 'portrait',
      unit: 'pt',
      format: 'a4',
    });

    const splitText = doc.splitTextToSize(markdownContent, 520);
    let y = 40;
    const pageHeight = doc.internal.pageSize.height;

    for (let i = 0; i < splitText.length; i++) {
      if (y > pageHeight - 40) {
        doc.addPage();
        y = 40;
      }
      doc.text(splitText[i], 40, y);
      y += 14;
    }

    doc.save(`Hardware_Report_${Date.now()}.pdf`);
  };

  return (
    <div className="flex gap-3 mt-4 pt-3 border-t border-slate-800">
      <button
        onClick={handleDownloadMarkdown}
        className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg transition-colors border border-slate-700"
      >
        <FileText size={14} /> Download Markdown (.md)
      </button>
      <button
        onClick={handleDownloadPDF}
        className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium bg-rose-950/60 hover:bg-rose-900/60 text-rose-300 rounded-lg transition-colors border border-rose-800/50"
      >
        <Download size={14} /> Download PDF (.pdf)
      </button>
    </div>
  );
}
