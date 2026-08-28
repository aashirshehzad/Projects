import React, { useState, useEffect } from 'react';
import Sidebar from './components/Sidebar';
import ChatFeed from './components/ChatFeed';
import { streamChat, fetchHistory, fetchThreads, deleteThread } from './services/api';
import { Send, Sparkles } from 'lucide-react';

export default function App() {
  const [threads, setThreads] = useState([]);
  const [activeThreadId, setActiveThreadId] = useState(crypto.randomUUID());
  const [messages, setMessages] = useState([]);
  const [inputQuery, setInputQuery] = useState('');
  const [filters, setFilters] = useState({
    useCase: 'Gaming',
    resolution: '1440p (QHD)',
    budget: 1500,
  });
  const [isStreaming, setIsStreaming] = useState(false);
  const [activeStatus, setActiveStatus] = useState(null);
  const [liveReportToken, setLiveReportToken] = useState('');

  // 1. Fetch available threads from Neon Postgres on initial load
  useEffect(() => {
    async function loadThreads() {
      try {
        const data = await fetchThreads();
        if (data && Array.isArray(data) && data.length > 0) {
          setThreads(data);
          setActiveThreadId(data[0].id);
        }
      } catch (err) {
        console.error('Failed to load threads on mount:', err);
      }
    }
    loadThreads();
  }, []);

  // 2. Fetch specific thread history whenever activeThreadId changes
  useEffect(() => {
    if (!activeThreadId) return;

    let isMounted = true;
    async function loadThreadHistory() {
      try {
        const data = await fetchHistory(activeThreadId);
        if (!isMounted) return;

        if (data && data.exists) {
          setMessages(data.messages || []);
          if (data.final_article) {
            setLiveReportToken(data.final_article);
          } else {
            setLiveReportToken('');
          }
          if (data.use_case || data.resolution || data.budget) {
            setFilters((prev) => ({
              useCase: data.use_case || prev.useCase,
              resolution: data.resolution || prev.resolution,
              budget: Number(String(data.budget).replace(/[^0-9]/g, '')) || prev.budget,
            }));
          }
        } else {
          // Brand new conversation session
          setMessages([]);
          setLiveReportToken('');
        }
      } catch (err) {
        if (!isMounted) return;
        console.log('No prior history or error loading thread history:', activeThreadId, err);
      }
    }

    loadThreadHistory();

    return () => {
      isMounted = false;
    };
  }, [activeThreadId]);

  const handleNewChat = () => {
    const newId = crypto.randomUUID();
    setMessages([]);
    setLiveReportToken('');
    setActiveStatus(null);
    setActiveThreadId(newId);
  };

  const handleDeleteThread = async (id) => {
    try {
      await deleteThread(id);
      setThreads((prev) => prev.filter((t) => t.id !== id));
      if (id === activeThreadId) {
        handleNewChat();
      }
    } catch (err) {
      console.error('Failed to delete thread:', id, err);
    }
  };

  const handleSendMessage = async (textToSend) => {
    const query = textToSend || inputQuery;
    if (!query.trim() || isStreaming) return;

    const userMessage = { role: 'user', content: query };
    setMessages((prev) => [...prev, userMessage]);
    setInputQuery('');
    setIsStreaming(true);
    setLiveReportToken('');
    setActiveStatus({ node: 'Researcher', status: 'running' });

    // Optimistically update threads list with user's prompt as title
    setThreads((prev) => {
      if (!prev.find((t) => t.id === activeThreadId)) {
        return [{ id: activeThreadId, title: query.slice(0, 30) }, ...prev];
      }
      return prev;
    });

    let accumulatedText = '';

    await streamChat({
      threadId: activeThreadId,
      query,
      budget: filters.budget,
      useCase: filters.useCase,
      resolution: filters.resolution,
      onStatus: (statusPayload) => {
        setActiveStatus(statusPayload);
      },
      onToken: (token) => {
        accumulatedText += token;
        setLiveReportToken(accumulatedText);
      },
      onDone: async () => {
        if (accumulatedText) {
          setMessages((prev) => [...prev, { role: 'assistant', content: accumulatedText }]);
        }
        setIsStreaming(false);
        setActiveStatus(null);
        setLiveReportToken('');

        // Refresh threads list from database
        try {
          const updatedThreads = await fetchThreads();
          if (updatedThreads && Array.isArray(updatedThreads) && updatedThreads.length > 0) {
            setThreads(updatedThreads);
          }
        } catch (e) {
          console.error('Error refreshing threads after chat completion:', e);
        }
      },
      onError: (err) => {
        console.error('Chat stream error:', err);
        setIsStreaming(false);
        setActiveStatus(null);
      },
    });
  };

  return (
    <div className="flex h-screen bg-slate-950 font-sans text-slate-100 overflow-hidden">
      <Sidebar
        threads={threads}
        activeThreadId={activeThreadId}
        onSelectThread={(id) => setActiveThreadId(id)}
        onDeleteThread={handleDeleteThread}
        onNewChat={handleNewChat}
        filters={filters}
        setFilters={setFilters}
      />

      <main className="flex-1 flex flex-col h-full bg-slate-950">
        {/* Top Bar Banner */}
        <header className="px-6 py-3 border-b border-slate-800 flex items-center justify-between bg-slate-900/50 backdrop-blur">
          <div className="text-xs text-slate-400">
            Workload: <span className="text-slate-200 font-medium">{filters.useCase}</span> • Res:{' '}
            <span className="text-slate-200 font-medium">{filters.resolution}</span> • Budget:{' '}
            <span className="text-indigo-400 font-semibold">${filters.budget}</span>
          </div>
        </header>

        {/* Conversation Feed */}
        <ChatFeed
          messages={messages}
          activeStatus={activeStatus}
          liveReportToken={liveReportToken}
        />

        {/* Input Dock */}
        <footer className="p-4 border-t border-slate-800 bg-slate-900/60">
          <div className="max-w-4xl mx-auto space-y-2.5">
            {messages.length === 0 && (
              <div className="flex gap-2 text-xs overflow-x-auto pb-1">
                {[
                  '🔥 Best $1,500 1440p Gaming Rig',
                  '⚡ Ryzen 7 7800X3D + RTX 4070 Ti Super',
                  '🤖 Budget AI / Local LLM Workstation',
                ].map((starter, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleSendMessage(starter)}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg whitespace-nowrap transition border border-slate-700"
                  >
                    <Sparkles size={12} className="text-indigo-400" /> {starter}
                  </button>
                ))}
              </div>
            )}

            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSendMessage();
              }}
              className="flex gap-2"
            >
              <input
                type="text"
                placeholder="Ask for a PC build or request adjustments (e.g., 'Switch to Intel', 'Make it $200 cheaper')..."
                value={inputQuery}
                onChange={(e) => setInputQuery(e.target.value)}
                disabled={isStreaming}
                className="flex-1 bg-slate-800 border border-slate-700 rounded-xl px-4 py-2.5 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={isStreaming || !inputQuery.trim()}
                className="px-4 py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-800 disabled:text-slate-600 text-white rounded-xl text-xs font-semibold flex items-center gap-1.5 transition"
              >
                <Send size={14} /> Send
              </button>
            </form>
          </div>
        </footer>
      </main>
    </div>
  );
}
