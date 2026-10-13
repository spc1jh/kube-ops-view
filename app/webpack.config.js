const path = require('path')
const webpack = require('webpack')
const pkg = require('./package.json')

module.exports = (env, argv) => {
    const debug = argv.mode !== 'production'
    return {
        context: __dirname,
        mode: debug ? 'development' : 'production',
        entry: './src/app.js',
        target: ['web', 'es2020'],
        devtool: debug ? 'inline-source-map' : false,
        output: {
            // exposes the App class as global `App` (see templates/index.html)
            library: {name: 'App', type: 'var', export: 'default'},
            path: path.resolve(__dirname, pkg.config.buildDir),
            publicPath: debug ? '/' : './',
            // the Flask index view globs for app*.js
            filename: debug ? 'app.js' : 'app-[contenthash].js',
            clean: true
        },
        plugins: [
            // keep a single app*.js file (pixi.js uses dynamic imports for optional renderers)
            new webpack.optimize.LimitChunkCountPlugin({maxChunks: 1})
        ],
        performance: {
            hints: false
        }
    }
}
