import { Routes, Route } from 'react-router-dom'
import { AppLayout } from '@/components/AppLayout'
import Home from '@/pages/Home'
import Library from '@/pages/Library'
import Monitor from '@/pages/Monitor'
import Creator from '@/pages/Creator'
import Settings from '@/pages/Settings'
import NotFound from '@/pages/NotFound'

function App() {
  return (
    <AppLayout>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/library" element={<Library />} />
        <Route path="/monitor" element={<Monitor />} />
        <Route path="/creator" element={<Creator />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </AppLayout>
  )
}

export default App
