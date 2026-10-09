type Fields = Record<string, unknown>;

function write(level: "info" | "error", message: string, fields: Fields): void {
  console.log(JSON.stringify({ time: new Date().toISOString(), level, message, ...fields }));
}

export const log = {
  info: (message: string, fields: Fields = {}) => write("info", message, fields),
  error: (message: string, fields: Fields = {}) => write("error", message, fields),
};
