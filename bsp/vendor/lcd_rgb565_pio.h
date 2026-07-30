#pragma once

#include <cstddef>
#include <cstdint>

void lcd_rgb565_pio_init(bool enable_dma);
void lcd_rgb565_pio_set_window(int x, int y, int w, int h);
void lcd_rgb565_pio_write_blocking(const uint16_t* pixels, int n_pixels);
void lcd_rgb565_pio_write_dma(const uint16_t* pixels, int n_pixels);
void lcd_rgb565_pio_wait_dma(void);
void lcd_rgb565_pio_fill_rect_blocking(int x, int y, int w, int h, uint16_t color);
void lcd_rgb565_pio_fill_rect_dma(int x, int y, int w, int h, uint16_t color);
