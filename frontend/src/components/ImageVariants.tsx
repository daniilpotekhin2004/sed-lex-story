import { useState, useEffect } from "react";
import { getSceneImages } from "../api/generation";

interface ImageVariant {
  id: string;
  image_url: string;
  created_at: string;
}

interface ImageVariantsProps {
  sceneId: string;
}

export default function ImageVariants({ sceneId }: ImageVariantsProps) {
  const [variants, setVariants] = useState<ImageVariant[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedImage, setSelectedImage] = useState<string | null>(null);

  useEffect(() => {
    loadVariants();
  }, [sceneId]);

  async function loadVariants() {
    try {
      setLoading(true);
      const data = await getSceneImages(sceneId);
      setVariants(data.variants || []);
    } catch (error) {
      console.error("Failed to load image variants:", error);
    } finally {
      setLoading(false);
    }
  }

  function formatDate(dateString: string) {
    const date = new Date(dateString);
    return date.toLocaleString();
  }

  if (loading) {
    return <div className="p-4">Загрузка изображений...</div>;
  }

  return (
    <div className="border rounded p-4 bg-white">
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-lg font-semibold">Сгенерированные изображения</h3>
        <button
          onClick={loadVariants}
          className="px-3 py-1 text-sm bg-gray-200 rounded hover:bg-gray-300"
        >Обновить</button>
      </div>

      {variants.length === 0 ? (
        <div className="text-center text-gray-500 py-8">
          Изображений пока нет. Используйте панель генерации, чтобы создать изображения.
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          {variants.map((variant) => (
            <div
              key={variant.id}
              className="border rounded overflow-hidden hover:shadow-lg transition cursor-pointer"
              onClick={() => setSelectedImage(variant.image_url)}
            >
              <img
                src={variant.image_url}
                alt={`Вариант ${variant.id}`}
                className="w-full h-48 object-cover"
              />
              <div className="p-2 bg-gray-50">
                <div className="text-xs text-gray-600">
                  {formatDate(variant.created_at)}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {selectedImage && (
        <div
          className="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center z-50 p-4"
          onClick={() => setSelectedImage(null)}
        >
          <div className="max-w-4xl max-h-full">
            <img
              src={selectedImage}
              alt="Полный размер"
              className="max-w-full max-h-full object-contain"
            />
          </div>
        </div>
      )}
    </div>
  );
}
