import api from './index'

export function login(username, password) {
  return api.post('/auth/login', { username, password })
}

export function register(username, email, password, inviteCode) {
  return api.post('/auth/register', { username, email, password, invite_code: inviteCode })
}

export function verifyInvite(code) {
  return api.post('/auth/verify-invite', { code })
}

export function forgotPassword(email) {
  return api.post('/auth/forgot-password', { email })
}

export function resetPassword(token, newPassword) {
  return api.post('/auth/reset-password', { token, new_password: newPassword })
}

export function changePassword(oldPassword, newPassword) {
  return api.post('/auth/change-password', { old_password: oldPassword, new_password: newPassword })
}

export function getMe() {
  return api.get('/auth/me')
}
