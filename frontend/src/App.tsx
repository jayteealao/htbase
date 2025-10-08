import { useMemo } from 'react'
import { Route, Routes } from 'react-router-dom'

import { AppShell } from './layouts/AppShell'
import DashboardPage from './features/dashboard/DashboardPage'
import SavesPage from './features/saves/SavesPage'
import CreateSavePage from './features/create-save/CreateSavePage'
import HtConsolePage from './features/ht-console/HtConsolePage'

export default function App() {
  return useMemo(
    () => (
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<DashboardPage />} />
          <Route path="/saves" element={<SavesPage />} />
          <Route path="/create" element={<CreateSavePage />} />
          <Route path="/ht-console" element={<HtConsolePage />} />
        </Route>
      </Routes>
    ),
    [],
  )
}
