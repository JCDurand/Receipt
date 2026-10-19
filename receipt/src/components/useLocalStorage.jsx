import { useState, useEffect } from "react";

export const useLocalStorage = (key, val) => {
    const [stored, setStored] = useState(() => {
        try {
            const item = localStorage.getItem(key);
            return item ? JSON.parse(item) : val;
        } catch (error) {
            console.error(error);
            return val;
        }
    });

    useEffect(() => {
        try {
            localStorage.setItem(key, JSON.stringify(stored));
        } catch (error) {
            console.error(error);
        }
    }, [key, stored]);

    return [stored, setStored];
}