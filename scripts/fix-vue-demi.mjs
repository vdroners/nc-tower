#!/usr/bin/env node
/**
 * vue-demi ships a shim that its own postinstall rewrites to match the
 * installed Vue major. npm refuses to run dependency install scripts under
 * several hardened configurations (`allowScripts`, `--ignore-scripts`, CI
 * defaults), and when that happens the shim stays on the plain Vue 2 build —
 * which does not export Fragment or TransitionGroup, so every @nextcloud/vue
 * component that reaches them fails to compile with a confusing
 * "export not found in vue-demi" error.
 *
 * Running the switch explicitly before webpack makes the build deterministic
 * whether or not install scripts were allowed.
 */
import { execFileSync } from 'node:child_process'
import { readdirSync, existsSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')

/**
 * Walk a node_modules tree. vue-demi is usually not hoisted — it lives under
 * each consumer, e.g. node_modules/@vueuse/core/node_modules/vue-demi — so
 * every package's own node_modules has to be visited, not just scope folders.
 *
 * @param {string} nodeModules a node_modules directory
 * @param {number} depth remaining recursion budget
 * @return {string[]} every vue-demi package directory found
 */
function findVueDemi(nodeModules, depth = 4) {
	if (depth < 0 || !existsSync(nodeModules)) {
		return []
	}
	const found = []
	for (const entry of readdirSync(nodeModules, { withFileTypes: true })) {
		if (!entry.isDirectory()) {
			continue
		}
		const full = join(nodeModules, entry.name)
		if (entry.name === 'vue-demi') {
			found.push(full)
			continue
		}
		if (entry.name.startsWith('@')) {
			// Scope folder: its children are packages, not a node_modules tree.
			for (const scoped of readdirSync(full, { withFileTypes: true })) {
				if (scoped.isDirectory()) {
					found.push(...findVueDemi(join(full, scoped.name, 'node_modules'), depth - 1))
				}
			}
			continue
		}
		found.push(...findVueDemi(join(full, 'node_modules'), depth - 1))
	}
	return found
}

const targets = findVueDemi(join(root, 'node_modules'))
if (!targets.length) {
	console.log('[fix-vue-demi] no vue-demi installs found — nothing to do')
	process.exit(0)
}

for (const target of targets) {
	const bin = join(target, 'bin', 'vue-demi-switch.js')
	if (!existsSync(bin)) {
		continue
	}
	execFileSync(process.execPath, [bin, '2.7'], { cwd: target, stdio: 'inherit' })
}
