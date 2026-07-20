import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Shield, Zap, Search, Lock, ArrowRight } from "lucide-react";

export default function LandingPage() {
  const navigate = useNavigate();

  return (
    <div className="w-full max-w-5xl mx-auto space-y-16 py-12 animate-in fade-in slide-in-from-bottom-8 duration-700">
      
      {/* Hero Section */}
      <div className="text-center space-y-6 max-w-3xl mx-auto">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-accent/10 text-accent text-sm font-medium border border-accent/20 mb-4">
          <Shield className="w-4 h-4" />
          <span>Telegram-only Knowledge Platform</span>
        </div>
        <h1 className="text-5xl md:text-6xl font-extrabold tracking-tight text-foreground">
          Your Second Brain for <span className="text-transparent bg-clip-text bg-gradient-to-r from-accent to-blue-500">Telegram</span>
        </h1>
        <p className="text-xl text-muted-foreground leading-relaxed">
          Nexora instantly securely indexes your Telegram chats, files, and links using Retrieval-Augmented Generation (RAG) to build a powerful AI workspace entirely out of your own conversations.
        </p>
        <div className="pt-8">
          <Button 
            size="lg" 
            className="rounded-full px-8 h-14 text-lg shadow-xl shadow-accent/20 transition-transform hover:scale-105"
            onClick={() => navigate("/telegram")}
          >
            Connect Telegram <ArrowRight className="ml-2 w-5 h-5" />
          </Button>
        </div>
      </div>

      {/* Feature Grid */}
      <div className="grid md:grid-cols-3 gap-6 pt-12">
        <div className="bg-surface/50 backdrop-blur-sm border border-border/50 p-8 rounded-2xl space-y-4">
          <div className="w-12 h-12 rounded-xl bg-blue-500/10 flex items-center justify-center text-blue-500">
            <Zap className="w-6 h-6" />
          </div>
          <h3 className="text-xl font-semibold">Live Sync</h3>
          <p className="text-muted-foreground">Continuous event-driven synchronization ensures your AI always has the latest context from your chats.</p>
        </div>
        
        <div className="bg-surface/50 backdrop-blur-sm border border-border/50 p-8 rounded-2xl space-y-4">
          <div className="w-12 h-12 rounded-xl bg-accent/10 flex items-center justify-center text-accent">
            <Search className="w-6 h-6" />
          </div>
          <h3 className="text-xl font-semibold">Semantic Search</h3>
          <p className="text-muted-foreground">Find answers instantly. Powered by ChromaDB and advanced vector embeddings to understand exactly what you mean.</p>
        </div>

        <div className="bg-surface/50 backdrop-blur-sm border border-border/50 p-8 rounded-2xl space-y-4">
          <div className="w-12 h-12 rounded-xl bg-success/10 flex items-center justify-center text-success">
            <Lock className="w-6 h-6" />
          </div>
          <h3 className="text-xl font-semibold">End-to-End Secure</h3>
          <p className="text-muted-foreground">Your phone number and session secrets are fully encrypted at rest. Nexora respects your privacy unconditionally.</p>
        </div>
      </div>
    </div>
  );
}
