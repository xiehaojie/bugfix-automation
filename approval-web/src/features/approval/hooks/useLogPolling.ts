import { useEffect } from "react";

export function useLogPolling(branch: string | undefined, refreshLog: (branch: string) => void | Promise<void>) {
  useEffect(() => {
    const logTimer = window.setInterval(() => {
      if (branch) void refreshLog(branch);
    }, 1000);
    return () => {
      window.clearInterval(logTimer);
    };
  }, [branch, refreshLog]);
}
