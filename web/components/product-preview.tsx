"use client";

import { useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";
import type { ProductCard } from "@/lib/contracts";

function detailText(value: unknown): string {
  if (value === null || value === undefined || value === "") return "Not provided";
  return typeof value === "object" ? JSON.stringify(value, null, 2) : String(value);
}

export function ProductPreview({ product, onClose }: {
  product: ProductCard;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const element = dialog.current!;
    const opener = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    element.showModal();
    document.body.style.overflow = "hidden";
    return () => {
      element.close();
      document.body.style.overflow = previousOverflow;
      if (opener instanceof HTMLElement && opener.isConnected) opener.focus();
    };
  }, []);

  return createPortal(
    <dialog ref={dialog} className="product-preview" aria-labelledby={titleId} onClose={() => {
      // Strict Mode reopens the dialog after effect cleanup. Ignore that
      // earlier close event if the dialog is already open again.
      if (!dialog.current?.open) onClose();
    }}>
      <div className="preview-toolbar">
        <span className="control-label">Catalog item · {product.parent_asin}</span>
        <button type="button" className="run-button secondary" onClick={onClose} autoFocus>
          Close preview
        </button>
      </div>
      <h2 id={titleId}>{product.title}</h2>
      <p className="preview-category">
        {product.categories.length ? product.categories.join(" › ") : "Category not provided"}
      </p>
      <dl className="preview-facts">
        <div><dt>Price</dt><dd>{product.price === null ? "Not provided" : `$${product.price.toFixed(2)}`}</dd></div>
        <div><dt>Store</dt><dd>{product.store || "Not provided"}</dd></div>
        <div><dt>Rating</dt><dd>{product.average_rating === null ? "Not provided" : `${product.average_rating.toFixed(1)} / 5`}</dd></div>
        <div><dt>Rating count</dt><dd>{product.rating_number === null ? "Not provided" : product.rating_number.toLocaleString()}</dd></div>
      </dl>
      <section>
        <h3>Features</h3>
        {product.features.length ? <ul>{product.features.map((feature, index) => <li key={index}>{feature}</li>)}</ul> : <p>No features provided.</p>}
      </section>
      <section>
        <h3>Description</h3>
        {product.description.length ? product.description.map((paragraph, index) => <p key={index}>{paragraph}</p>) : <p>No description provided.</p>}
      </section>
      <section>
        <h3>Specifications</h3>
        {Object.keys(product.details).length ? (
          <dl className="preview-specs">
            {Object.entries(product.details).map(([key, value]) => (
              <div key={key}><dt>{key}</dt><dd>{detailText(value)}</dd></div>
            ))}
          </dl>
        ) : <p>No specifications provided.</p>}
      </section>
    </dialog>,
    document.body,
  );
}
