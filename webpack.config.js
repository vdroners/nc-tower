const path = require('path')
const { merge } = require('webpack-merge')
const baseConfig = require('@nextcloud/webpack-vue-config')

// One bundle for all seven pages. Each PHP template mounts #nc_tower with a
// data-page attribute; src/main.js picks the view. Output name matches the
// Util::addScript('nc_tower', 'nc_tower-app') call in the templates.
const config = merge(baseConfig, {
	// Source maps for this bundle are ~5 MB and would be copied into the
	// container on every deploy; the app is debuggable from src/ instead.
	devtool: false,
	output: {
		path: path.resolve(__dirname, 'js'),
		filename: 'nc_tower-[name].js',
		chunkFilename: 'nc_tower-[name].[contenthash].js',
		publicPath: 'auto',
		// Regenerate js/ each build so stale hashed chunks never linger.
		clean: true,
	},
	resolve: {
		alias: {
			'@': path.resolve(__dirname, 'src'),
		},
	},
})

// Replace rather than merge: the base config declares its own `main` entry,
// and merging would emit a second identical bundle under the old upstream
// filename.
config.entry = {
	app: path.resolve(__dirname, 'src', 'main.js'),
	widget: path.resolve(__dirname, 'src', 'widget.js'),
}

module.exports = config
