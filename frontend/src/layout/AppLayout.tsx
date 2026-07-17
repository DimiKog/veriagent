import { NavLink, Outlet } from 'react-router-dom'
import {
  API_DOCS_URL,
  CONTRACT_EXPLORER_URL,
} from '../api/client'
import { ExternalLinkIcon, ShieldIcon } from '../components/Icons'

const NAV_LINKS = [
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/register', label: 'Register' },
  { to: '/console', label: 'Console' },
  { to: '/admin', label: 'Admin' },
] as const

export function AppLayout() {
  return (
    <div className="dashboard">
      <header className="dashboard__header">
        <div className="dashboard__header-top">
          <div className="dashboard__logo" aria-hidden="true">
            <ShieldIcon />
          </div>
          <h1>
            VeriAgent
            <span className="dashboard__version">v1.0.0-rc.1</span>
          </h1>
          <nav className="app-nav" aria-label="Primary">
            {NAV_LINKS.map(({ to, label }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  isActive ? 'app-nav__link app-nav__link--active' : 'app-nav__link'
                }
              >
                {label}
              </NavLink>
            ))}
          </nav>
          <nav className="dashboard__nav" aria-label="External links">
            <a href={API_DOCS_URL} target="_blank" rel="noopener noreferrer">
              API Docs <ExternalLinkIcon />
            </a>
            <span aria-hidden="true">·</span>
            <a
              href="https://github.com/DimiKog/veriagent"
              target="_blank"
              rel="noopener noreferrer"
            >
              GitHub
            </a>
            <span aria-hidden="true">·</span>
            <a href={CONTRACT_EXPLORER_URL} target="_blank" rel="noopener noreferrer">
              Contract
            </a>
          </nav>
        </div>
        <p className="dashboard__tagline">
          Audit events are hashed and committed on-chain — only cryptographic proofs are anchored
          to Besu Edu-Net, never raw data.
        </p>
      </header>

      <Outlet />
    </div>
  )
}
