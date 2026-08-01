from __future__ import annotations


def install_dojo_responsive_order(base_class):
    """Keep the 64×64 card before 32×32 while applying responsive reflow."""

    class OrderedResponsiveDojoUI(base_class):
        def _dojo_apply_responsive_layout(self) -> None:
            self._dojo_resize_after = None
            body = self._dojo_summary_body
            left = self._dojo_summary_left
            right = self._dojo_summary_right
            image_grid = self._dojo_images_grid
            if body is None or left is None or right is None:
                return
            try:
                width = max(1, int(self.root.winfo_width()))
            except Exception:
                width = 1280
            compact = width < 1220
            left.grid_forget()
            right.grid_forget()
            if compact:
                body.grid_columnconfigure(0, weight=1)
                body.grid_columnconfigure(1, weight=0)
                body.grid_rowconfigure(0, weight=0)
                body.grid_rowconfigure(1, weight=1)
                right.grid(row=0, column=0, sticky="ew")
                left.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
            else:
                body.grid_columnconfigure(0, weight=3)
                body.grid_columnconfigure(1, weight=2)
                body.grid_rowconfigure(0, weight=1)
                body.grid_rowconfigure(1, weight=0)
                left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
                right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

            if image_grid is None:
                return
            for child in image_grid.grid_slaves():
                child.grid_forget()
            # winfo_children preserves creation order: 64×64 was created first, then 32×32.
            cards = list(image_grid.winfo_children())
            if compact:
                image_grid.grid_columnconfigure(0, weight=1)
                image_grid.grid_columnconfigure(1, weight=0)
                for row, card in enumerate(cards):
                    card.grid(
                        row=row,
                        column=0,
                        sticky="ew",
                        pady=(0 if row == 0 else 6, 6),
                    )
            else:
                image_grid.grid_columnconfigure(0, weight=1, uniform="dojo_images")
                image_grid.grid_columnconfigure(1, weight=1, uniform="dojo_images")
                for column, card in enumerate(cards):
                    card.grid(
                        row=0,
                        column=column,
                        sticky="nsew",
                        padx=(0 if column == 0 else 6, 0 if column == 1 else 6),
                    )

    return OrderedResponsiveDojoUI


__all__ = ["install_dojo_responsive_order"]
