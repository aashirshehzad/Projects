import React from 'react';
import { Plus, MessageSquare, Sliders, Cpu, Trash2 } from 'lucide-react';

export default function Sidebar({
  threads,
  activeThreadId,
  onSelectThread,
  onDeleteThread,
  onNewChat,
  filters,
  setFilters,
}) {
  return (
    <aside className="w-80 bg-slate-900 border-r border-slate-800 flex flex-col h-screen text-slate-200">
      {/* App Header */}
      <div className="p-4 border-b border-slate-800 flex items-center gap-2.5">
        <div className="p-2 bg-indigo-600/20 text-indigo-400 rounded-lg border border-indigo-500/30">
          <Cpu size={20} />
        </div>
        <div>
          <h1 className="font-bold text-sm tracking-wide text-slate-100">Hardware AI Hub</h1>
          <p className="text-[11px] text-slate-400">Multi-Agent Researcher</p>
        </div>
      </div>

      {/* New Chat Button */}
      <div className="p-3">
        <button
          onClick={onNewChat}
          className="w-full flex items-center justify-center gap-2 py-2 px-3 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold rounded-lg shadow transition"
        >
          <Plus size={16} /> New Hardware Chat
        </button>
      </div>

      {/* Recent Chats */}
      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-1">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 px-2 mb-1.5 flex items-center gap-1.5">
          <MessageSquare size={13} /> Recent Chats
        </div>
        {threads.length === 0 ? (
          <div className="text-xs text-slate-600 px-2 py-3 italic">No past chats found</div>
        ) : (
          threads.map((t) => (
            <div
              key={t.id}
              onClick={() => onSelectThread(t.id)}
              className={`group w-full px-3 py-2 rounded-lg text-xs transition flex justify-between items-center cursor-pointer ${
                activeThreadId === t.id
                  ? 'bg-slate-800 text-indigo-400 font-medium border border-indigo-500/20'
                  : 'hover:bg-slate-800/60 text-slate-400'
              }`}
            >
              <div className="flex items-center gap-2 min-w-0 flex-1 mr-2">
                <MessageSquare size={13} className="shrink-0" />
                <span className="truncate">{t.title || 'Hardware Inquiry'}</span>
              </div>
              <button
                type="button"
                title="Delete chat"
                onClick={(e) => {
                  e.stopPropagation();
                  if (onDeleteThread) onDeleteThread(t.id);
                }}
                className="opacity-0 group-hover:opacity-100 p-1 text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 rounded transition shrink-0"
              >
                <Trash2 size={13} />
              </button>
            </div>
          ))
        )}
      </div>

      {/* Build Configuration / Filters */}
      <div className="p-4 border-t border-slate-800 bg-slate-950/40 space-y-3.5">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
          <Sliders size={13} /> Build Configuration
        </div>

        <div>
          <label className="text-xs text-slate-400 block mb-1">Primary Use Case</label>
          <select
            value={filters.useCase}
            onChange={(e) => setFilters({ ...filters, useCase: e.target.value })}
            className="w-full bg-slate-800 border border-slate-700 text-xs rounded-lg px-2.5 py-1.5 text-slate-200 focus:outline-none focus:border-indigo-500"
          >
            <option>Gaming</option>
            <option>Video Editing & 3D Rendering</option>
            <option>AI & Deep Learning</option>
            <option>Office & General Productivity</option>
          </select>
        </div>

        <div>
          <label className="text-xs text-slate-400 block mb-1">Target Resolution</label>
          <select
            value={filters.resolution}
            onChange={(e) => setFilters({ ...filters, resolution: e.target.value })}
            className="w-full bg-slate-800 border border-slate-700 text-xs rounded-lg px-2.5 py-1.5 text-slate-200 focus:outline-none focus:border-indigo-500"
          >
            <option>1080p (FHD)</option>
            <option>1440p (QHD)</option>
            <option>4K (UHD)</option>
            <option>Standard Workstation</option>
          </select>
        </div>

        <div>
          <div className="flex justify-between text-xs text-slate-400 mb-1">
            <span>Budget (USD)</span>
            <span className="font-semibold text-indigo-400">${filters.budget}</span>
          </div>
          <input
            type="range"
            min="500"
            max="5000"
            step="50"
            value={filters.budget}
            onChange={(e) => setFilters({ ...filters, budget: Number(e.target.value) })}
            className="w-full accent-indigo-500 h-1.5 bg-slate-800 rounded-lg cursor-pointer"
          />
        </div>
      </div>
    </aside>
  );
}
