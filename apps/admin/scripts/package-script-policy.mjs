const FORBIDDEN_PACKAGE_MANAGER_PATTERN =
  /(^|[;&|]\s*)(npm\s+(run|exec|install|add|test|lint|build)\b|yarn(\s|$))/

export function findForbiddenPackageScripts(scripts = {}) {
  return Object.entries(scripts)
    .filter(([, command]) => FORBIDDEN_PACKAGE_MANAGER_PATTERN.test(command))
}
