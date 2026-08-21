"use client";

import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = { children: ReactNode };
type State = { hasError: boolean; message: string };

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, message: "" };

  static getDerivedStateFromError(error: Error): State {
    return {
      hasError: true,
      message: error?.message || "Beklenmeyen bir hata oluştu.",
    };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("TİLKO ErrorBoundary", error, info.componentStack);
  }

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }
    return (
      <div className="flex min-h-[50vh] flex-col items-center justify-center gap-4 px-6 py-16 text-center">
        <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-orange-600 dark:text-orange-300">
          TİLKO
        </p>
        <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
          Sayfa takıldı
        </h1>
        <p className="max-w-md text-sm text-zinc-600 dark:text-zinc-400">
          {this.state.message} Yenile; devam ederse oturumu kapatıp tekrar gir.
        </p>
        <button
          type="button"
          className="rounded-full bg-orange-500 px-5 py-2 text-sm font-semibold text-white hover:bg-orange-400"
          onClick={() => {
            this.setState({ hasError: false, message: "" });
            window.location.reload();
          }}
        >
          Yenile
        </button>
      </div>
    );
  }
}
