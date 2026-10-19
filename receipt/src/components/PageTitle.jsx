import { createContext, useContext, useEffect, useMemo, useState } from "react";

const PageTitleContext = createContext({ title: "", setTitle: () => {} });

/* Holds the title of the page being shown, for the preferences bar to display */
export const PageTitleProvider = ({ children }) => {
  const [title, setTitle] = useState("");
  const value = useMemo(() => ({ title, setTitle }), [title]);
  return <PageTitleContext.Provider value={value}>{children}</PageTitleContext.Provider>;
};

export const useShownTitle = () => useContext(PageTitleContext).title;

/* A page calls this with its title, which then appears in the preferences bar
   (in place of a heading of its own) for as long as the page is shown */
export const usePageTitle = (title) => {
  const { setTitle } = useContext(PageTitleContext);
  useEffect(() => {
    setTitle(title || "");
    return () => setTitle("");
  }, [title, setTitle]);
};
