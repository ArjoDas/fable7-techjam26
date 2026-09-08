import type { ProductCard } from "@/lib/contracts";

function initials(value: string): string {
  return value
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

export function ProductGrid({ products }: { products: ProductCard[] }) {
  if (!products.length) {
    return (
      <div className="empty-products">
        <span>◇</span>
        <p>Your recommendations will collect here.</p>
      </div>
    );
  }

  return (
    <div className="product-grid">
      {products.map((product, index) => (
        <article className="product-card" key={product.parent_asin}>
          <div className={`product-art art-${index % 5}`}>
            <span>{initials(product.category || product.store || "Pick")}</span>
            <small>#{String(index + 1).padStart(2, "0")}</small>
          </div>
          <div className="product-content">
            <div className="product-meta">
              <span>{product.category || "Catalog pick"}</span>
              {product.average_rating !== null && (
                <span>★ {product.average_rating.toFixed(1)}</span>
              )}
            </div>
            <h3>{product.title}</h3>
            {product.feature && <p>{product.feature}</p>}
            <div className="product-bottom">
              <strong>{product.price === null ? "Price unavailable" : `$${product.price.toFixed(2)}`}</strong>
              <span>{product.store}</span>
            </div>
          </div>
        </article>
      ))}
    </div>
  );
}

