module.exports = {
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.js",
    globals: true,
    include: ["src/__tests__/**/*.{js,jsx}"],
  },
};
