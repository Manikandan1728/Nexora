import { Link } from "react-router-dom";
import { Brain, ArrowLeft } from "lucide-react";

export default function NotFoundPage() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-6 text-center animate-fade-in">
      {/* Large 404 */}
      <div className="relative">
        <p className="text-[8rem] font-black text-surface-hover leading-none select-none">
          404
        </p>
        <div className="absolute inset-0 flex items-center justify-center">
          <Brain className="h-16 w-16 text-accent opacity-80" aria-hidden="true" />
        </div>
      </div>

      <div className="space-y-2">
        <h1 className="text-2xl font-bold text-foreground">Page not found</h1>
        <p className="text-sm text-muted-foreground max-w-xs">
          The page you're looking for doesn't exist or has been moved.
        </p>
      </div>

      <Link
        to="/"
        className="flex items-center gap-2 rounded-lg bg-accent px-5 py-2.5 text-sm font-semibold text-accent-foreground hover:opacity-90 transition-opacity"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        Back to Dashboard
      </Link>
    </div>
  );
}
