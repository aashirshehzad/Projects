// Presentation metadata for each tool the agent can call.
export const TOOL_META = {
  get_weather: { icon: "⛅", label: "Weather", accent: "#38bdf8" },
  get_stock_price: { icon: "📈", label: "Stocks", accent: "#34d399" },
  calculator: { icon: "🧮", label: "Calculator", accent: "#f59e0b" },
  convert_units: { icon: "🔄", label: "Units & FX", accent: "#a78bfa" },
  wikipedia_lookup: { icon: "📖", label: "Wikipedia", accent: "#94a3b8" },
  web_search: { icon: "🔍", label: "Web search", accent: "#60a5fa" },
  get_current_time: { icon: "🕐", label: "Time", accent: "#f472b6" },
  define_word: { icon: "📝", label: "Dictionary", accent: "#2dd4bf" },
  get_news: { icon: "📰", label: "News", accent: "#fb923c" },
};

export const meta = (name) =>
  TOOL_META[name] || { icon: "🔧", label: name, accent: "#8b93a1" };

export const SUGGESTIONS = [
  { icon: "⛅", text: "What's the weather in Lahore right now?" },
  { icon: "📈", text: "Price of TSLA and how it moved today, in PKR" },
  { icon: "🧮", text: "What is 15% of 2340, then the square root of that?" },
  { icon: "📖", text: "Give me a 2-line summary of the Eiffel Tower" },
  { icon: "🕐", text: "What time is it in Tokyo and New York?" },
  { icon: "📰", text: "Latest news about electric vehicles" },
];
