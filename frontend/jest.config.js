export default {
  testEnvironment: "jsdom",
  setupFilesAfterEnv: ["<rootDir>/src/test/setup.js"],
  moduleNameMapper: {
    "\\.(css|less|scss)$": "<rootDir>/src/test/styleMock.js"
  }
};
