export interface Credentials {
	username: string;
	password: string;
}

// openapi-fetch sends JSON by default: the serializer replaces the body and the header replaces the content type.
export const formBody = {
	bodySerializer: ({ username, password }: Credentials) =>
		new URLSearchParams({ username, password }),
	headers: { "Content-Type": "application/x-www-form-urlencoded" },
};
