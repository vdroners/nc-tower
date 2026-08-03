const path = require('path')
const { defineConfig } = require('vitest/config')

// Mirrors nc-print's setup so the estate has one test story: happy-dom for
// every spec, specs under src/__tests__/, `npm run test` to run them.
module.exports = defineConfig({
	test: {
		environment: 'happy-dom',
		include: ['src/__tests__/**/*.spec.js'],
		clearMocks: true,
	},
	resolve: {
		alias: {
			'@': path.resolve(__dirname, 'src'),
		},
	},
})
