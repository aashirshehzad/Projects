import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Bot, User, Search, Brain, PenTool, Loader2 } from 'lucide-react';
import ExportButtons from './ExportButtons';

const agentSteps = [
  { key: 'researcher', label: 'Researcher', desc: 'Tavily live pricing & specs', icon: Search },
  { key: 'analyst', label: 'Analyst', desc: 'Bottleneck & balance critique', icon: Brain },
  { key: 'writer', label: 'Writer', desc: 'Synthesizing final report', icon: PenTool },
];

export default function ChatFeed({ messages, activeStatus, liveReportToken }) {
  return (
    <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
      {messages.map((msg, index) => {
        const isUser = msg.role === 'user' || msg.type === 'human';
        return (
          <div
            key={index}
            className={`flex gap-3.5 max-w-4xl mx-auto ${isUser ? 'justify-end' : 'justify-start'}`}
          >
            {!isUser && (
              <div className="w-8 h-8 rounded-lg bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center text-indigo-400 shrink-0 mt-0.5">
                <Bot size={17} />
              </div>
            )}
            <div
              className={`rounded-xl p-4 text-xs leading-relaxed max-w-[85%] ${
                isUser
                  ? 'bg-indigo-600 text-white rounded-br-none shadow-md'
                  : 'bg-slate-900 border border-slate-800 text-slate-200 rounded-bl-none prose prose-invert max-w-none'
              }`}
            >
              {isUser ? (
                <p className="whitespace-pre-wrap">{msg.content}</p>
              ) : (
                <>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                  <ExportButtons markdownContent={msg.content} />
                </>
              )}
            </div>
            {isUser && (
              <div className="w-8 h-8 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-300 shrink-0 mt-0.5">
                <User size={17} />
              </div>
            )}
          </div>
        );
      })}

      {/* Live Pipeline Stepper Status */}
      {activeStatus && (
        <div className="max-w-4xl mx-auto bg-slate-900/90 border border-indigo-500/30 rounded-xl p-4 shadow-lg">
          <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-2">
            <Loader2 size={13} className="animate-spin text-indigo-400" />
            Multi-Agent Pipeline Executing
          </div>
          <div className="grid grid-cols-3 gap-3">
            {agentSteps.map((s) => {
              const Icon = s.icon;
              const isCurrent = activeStatus.node?.toLowerCase().includes(s.key);
              return (
                <div
                  key={s.key}
                  className={`p-2.5 rounded-lg border text-xs flex items-center gap-2.5 transition ${
                    isCurrent
                      ? 'border-indigo-500 bg-indigo-950/40 text-indigo-200'
                      : 'border-slate-800 bg-slate-950/50 text-slate-500'
                  }`}
                >
                  <Icon size={16} className={isCurrent ? 'text-indigo-400 animate-pulse' : 'text-slate-600'} />
                  <div>
                    <div className="font-medium text-[11px]">{s.label}</div>
                    <div className="text-[10px] text-slate-400">{s.desc}</div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Live Streaming Token Preview */}
          {liveReportToken && (
            <div className="mt-4 pt-3 border-t border-slate-800 text-xs text-slate-300 prose prose-invert max-w-none">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{liveReportToken}</ReactMarkdown>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
