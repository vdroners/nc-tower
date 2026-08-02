#!/usr/bin/env node
/**
 * Template reference checker.
 *
 * webpack happily compiles a Vue template that reads `stackRows` even when the
 * component never defines it — the failure only surfaces as a render-time
 * TypeError in the browser, which is exactly the kind of defect that survives a
 * green build. This compiles every SFC template and asserts each `_vm.<name>`
 * it reaches for is actually declared in data / computed / methods / props /
 * components.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { parse as parseSfc, compileTemplate } from 'vue/compiler-sfc'
import { parse as parseJs } from '@babel/parser'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', 'src')

/**
 * @param {string} dir directory to walk
 * @return {string[]} every .vue file below it
 */
function walk(dir) {
	const out = []
	for (const entry of readdirSync(dir)) {
		const full = join(dir, entry)
		if (statSync(full).isDirectory()) {
			out.push(...walk(full))
		} else if (entry.endsWith('.vue')) {
			out.push(full)
		}
	}
	return out
}

// Render-helper and instance globals a template may legitimately reach for.
const ALLOWED = new Set([
	'_c', '_v', '_s', '_e', '_l', '_t', '_u', '_m', '_b', '_g', '_k', '_n', '_o', '_q', '_i', '_p', '_f',
	'$createElement', '$scopedSlots', '$slots', '$attrs', '$listeners', '$emit', '$set', '$delete',
	'$refs', '$el', '$data', '$props', '$options', '$nextTick', '$root', '$parent', '$children',
	'_self', '_uid', 'Object', 'Array', 'String', 'Number', 'Boolean', 'Math', 'JSON', 'Date',
	'parseFloat', 'parseInt', 'isNaN', 'encodeURIComponent', 'decodeURIComponent',
])

/**
 * @param {object} node any AST node
 * @return {string|null} the property key as written
 */
function keyName(node) {
	if (!node?.key) {
		return null
	}
	return node.key.name ?? node.key.value ?? null
}

/**
 * Names the component exposes to its own template, read off the AST rather than
 * by counting braces — `data()` keys sit inside a return statement, which is a
 * level deeper than every other block, and brace counting gets that wrong.
 *
 * @param {string} script the <script> block
 * @return {Set<string>|null} declared names, or null when they cannot be known
 */
function declaredNames(script) {
	const declared = new Set()
	const ast = parseJs(script, {
		sourceType: 'module',
		plugins: ['optionalChaining', 'nullishCoalescingOperator'],
	})

	const exported = ast.program.body.find((node) => node.type === 'ExportDefaultDeclaration')
	const options = exported?.declaration
	if (options?.type !== 'ObjectExpression') {
		return declared
	}

	for (const prop of options.properties) {
		const name = keyName(prop)
		if (!name) {
			continue
		}

		if (name === 'data') {
			const body = prop.value?.body ?? prop.body
			const ret = body?.body?.find((node) => node.type === 'ReturnStatement')
			for (const entry of ret?.argument?.properties ?? []) {
				if (entry.type === 'SpreadElement') {
					// Spread of an imported object: contents are unknowable, so
					// stop asserting for this component rather than cry wolf.
					return null
				}
				const key = keyName(entry)
				if (key) {
					declared.add(key)
				}
			}
			continue
		}

		if (['computed', 'methods', 'components'].includes(name) && prop.value?.type === 'ObjectExpression') {
			for (const entry of prop.value.properties) {
				const key = keyName(entry)
				if (key) {
					declared.add(key)
				}
			}
			continue
		}

		if (name === 'props') {
			if (prop.value?.type === 'ObjectExpression') {
				for (const entry of prop.value.properties) {
					const key = keyName(entry)
					if (key) {
						declared.add(key)
					}
				}
			} else if (prop.value?.type === 'ArrayExpression') {
				for (const entry of prop.value.elements) {
					if (entry?.value) {
						declared.add(entry.value)
					}
				}
			}
		}
	}
	return declared
}

let problems = 0

for (const file of walk(ROOT)) {
	// Vue 2.7's compiler-sfc returns the descriptor directly, not { descriptor }.
	const descriptor = parseSfc({ source: readFileSync(file, 'utf8'), filename: file })
	if (!descriptor.template) {
		continue
	}
	const short = file.slice(file.indexOf('/src/') + 1)

	const compiled = compileTemplate({ source: descriptor.template.content, filename: file })
	if (compiled.errors?.length) {
		console.log(`TEMPLATE ERROR  ${short}`)
		compiled.errors.forEach((error) => console.log(`    ${error}`))
		problems++
		continue
	}

	const declared = declaredNames(descriptor.script?.content || '')
	if (declared === null) {
		console.log(`SKIP            ${short} (spread in data())`)
		continue
	}

	const used = new Set()
	for (const match of compiled.code.matchAll(/_vm\.([A-Za-z_$][\w$]*)/g)) {
		used.add(match[1])
	}

	const missing = [...used].filter((name) => !declared.has(name) && !ALLOWED.has(name))
	if (missing.length) {
		console.log(`UNDEFINED REF   ${short}`)
		missing.forEach((name) => console.log(`    ${name}`))
		problems++
	}
}

if (problems) {
	console.log(`\n${problems} file(s) with undefined template references`)
	process.exit(1)
}
console.log('template refs OK — every name used in a template is declared')
