// ============================================================================
// 主应用组件
// ============================================================================

import { useEffect } from 'react';
import { RouterProvider } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useFirebase } from './hooks/useFirebase';
import { useUIStore } from './store/uiStore';
import { router } from './router';
import Spinner from './components/common/Spinner';

// 创建 React Query 客户端
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 5 * 60 * 1000, // 5 分钟
    },
  },
});

export default function App() {
  const { initialized, error } = useFirebase();
  const { theme } = useUIStore();

  // 应用主题
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  if (error) {
    return (
      <div style={{ padding: '20px', textAlign: 'center' }}>
        <h2>Firebase 初始化失败</h2>
        <p>{error}</p>
      </div>
    );
  }

  if (!initialized) {
    return <Spinner size="large" message="Initializing..." />;
  }

  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
