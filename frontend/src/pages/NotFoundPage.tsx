import { ArrowLeft, Compass } from "lucide-react";
import { Link } from "react-router-dom";

import { PageHeader } from "../components/Primitives";

export function NotFoundPage() {
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="404"
        title="This route holds no records."
        description="The page may have moved, or the identifier does not exist in the selected dataset."
        actions={
          <Link className="button button--primary button--md" to="/">
            <ArrowLeft size={15} /> Back to overview
          </Link>
        }
      />
      <div className="empty-state empty-state--page">
        <span className="empty-state__icon"><Compass size={24} /></span>
        <h3>Nothing to reconcile here</h3>
        <p>Use the console navigation to return to a trusted view.</p>
      </div>
    </div>
  );
}
