import { useEffect } from "react";

export function useAutoRefresh(refresh: () => void | Promise<void>) {
  useEffect(() => {
    const refreshTimer = window.setInterval(() => {
      void refresh();
    }, 10000);
    return () => {
      window.clearInterval(refreshTimer);
    };
  }, [refresh]);
}
