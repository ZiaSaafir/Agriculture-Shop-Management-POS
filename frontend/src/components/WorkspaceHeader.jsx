import RoleNavigation from './RoleNavigation.jsx'

export default function WorkspaceHeader({
  user,
  branches,
  branchId,
  eyebrow,
  title,
  detail,
  onSignOut,
}) {
  const selectedBranch = branches?.find(
    (branch) => String(branch.id) === String(branchId),
  )
  const organizationName = selectedBranch?.organization || 'Shop workspace'
  const branchName = selectedBranch?.name || 'Choose an active branch'

  return (
    <header className="pos-header">
      <div className="workspace-brand">
        <span aria-hidden="true" className="workspace-brand-mark">
          {organizationName.trim().charAt(0).toLocaleUpperCase()}
        </span>
        <div className="workspace-brand-copy">
          <p className="workspace-organization">{organizationName}</p>
          <p className="workspace-branch">{branchName}</p>
        </div>
      </div>
      <div className="workspace-page-title">
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        {detail && <p className="pos-user">{detail}</p>}
      </div>
      <div className="workspace-account">
        <span aria-hidden="true" className="workspace-avatar">
          {(user.first_name || user.username).trim().charAt(0).toLocaleUpperCase()}
        </span>
        <div className="workspace-account-copy">
          <strong>{user.first_name || user.username}</strong>
          <span>Role: {user.roles.join(', ') || 'No role assigned'}</span>
        </div>
        <button
          className="button-secondary"
          onClick={onSignOut}
          type="button"
        >
          Sign out
        </button>
      </div>
      <RoleNavigation user={user} />
    </header>
  )
}
