// craco.config.js
//
// The production build writes straight into ../static/react/ with *stable*, unhashed
// filenames, and emits no index.html. That is deliberate:
//
//   - The backend serves the SPA shell itself (templates/index.html) so it can set the
//     CSRF cookie and inject server-side values (the signed-in user, static() asset URLs).
//   - Cache-busting is done by the backend: roomchat/staticfiles.py static() appends
//     ?v=<content hash> to each URL it renders, so a rebuilt file gets a new URL. A URL
//     webpack hardcodes gets no hash, so webpack must not hardcode any.
//   - For the same reason code splitting is off: a lazily-loaded chunk URL is baked into
//     the bundle at build time and never gets a ?v= hash. Five pages, one bundle.
//
// Corollary: do NOT `import` images or fonts from src/. Webpack would emit them with a
// URL the backend never hashes. Put them in public/ and pass the static() URL through
// the bootstrap blob in templates/index.html, as the landing hero does.

const path = require("path");

const BUILD_DIR = path.resolve(__dirname, "..", "static", "react");

module.exports = {
  // Point react-scripts' own notion of the build directory at static/react too.
  // Without this it would empty frontend/build, copy public/ there, and then fail
  // looking for the bundle it never wrote — exiting 1 on an otherwise good build.
  // Note this means `yarn build` empties static/react: everything in it is generated
  // or copied from public/, so nothing hand-placed can live there.
  paths: (paths) => ({ ...paths, appBuild: BUILD_DIR }),

  eslint: {
    configure: {
      extends: ["plugin:react-hooks/recommended"],
      rules: {
        "react-hooks/rules-of-hooks": "error",
        "react-hooks/exhaustive-deps": "warn",
      },
    },
  },

  webpack: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
    configure: (webpackConfig) => {
      webpackConfig.watchOptions = {
        ...webpackConfig.watchOptions,
        ignored: ["**/node_modules/**", "**/.git/**", "**/build/**"],
      };

      if (process.env.NODE_ENV !== "production") {
        return webpackConfig;
      }

      webpackConfig.output.path = BUILD_DIR;
      webpackConfig.output.filename = "js/main.js";
      webpackConfig.output.publicPath = "";

      webpackConfig.optimization.splitChunks = { cacheGroups: { default: false } };
      webpackConfig.optimization.runtimeChunk = false;

      // No source map: it would be committed alongside the bundle and collected into
      // staticfiles for no benefit. Flip this locally if you need to debug the build.
      webpackConfig.devtool = false;

      // Drop the plugins that exist only to produce or rewrite CRA's own index.html,
      // and pin the extracted stylesheet to a stable name.
      webpackConfig.plugins = webpackConfig.plugins.filter((plugin) => {
        const name = plugin.constructor.name;
        if (name === "HtmlWebpackPlugin") return false;
        if (name === "InlineChunkHtmlPlugin") return false;
        if (name === "InterpolateHtmlPlugin") return false;
        if (name === "WebpackManifestPlugin") return false;
        if (name === "MiniCssExtractPlugin") {
          plugin.options.filename = "css/main.css";
          plugin.options.chunkFilename = "css/[name].css";
        }
        return true;
      });

      return webpackConfig;
    },
  },
};
