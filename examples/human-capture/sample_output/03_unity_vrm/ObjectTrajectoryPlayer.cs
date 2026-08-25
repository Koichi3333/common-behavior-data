using System;
using UnityEngine;

// Common Behavior Data の物体軌跡をUnityでキネマティック再生する。
// 使い方: object_trajectory_unity.json と本ファイルを Assets へ入れ、
// 空のGameObjectに本コンポーネントを追加して trajectoryJson を割り当てる。
// 再生中に Space キーで先頭から再同期（アバターのループ頭に合わせる用）。
public class ObjectTrajectoryPlayer : MonoBehaviour
{
    [Serializable] public class TrajectoryFrame
    { public float t; public float x; public float y; public float z; public string source; }
    [Serializable] public class ObjectTrajectory
    { public string label; public string shape; public float fps; public float size;
      public TrajectoryFrame[] frames; }

    [Tooltip("object_trajectory_unity.json を割り当て")]
    public TextAsset trajectoryJson;
    public bool loop = true;
    [Tooltip("UniVRM(VRM 1.0)のX反転に合わせる。左右が逆ならOFF")]
    public bool mirrorX = true;
    [Tooltip("再生時刻オフセット[秒]。矢印キー←→でも実行中に調整可")]
    public float timeOffset = 0f;

    ObjectTrajectory data;
    Transform target;
    float startTime;

    void Start()
    {
        if (trajectoryJson == null)
        { Debug.LogWarning("trajectoryJson が未割り当てです"); enabled = false; return; }
        data = JsonUtility.FromJson<ObjectTrajectory>(trajectoryJson.text);
        if (data == null || data.frames == null || data.frames.Length == 0)
        { Debug.LogWarning("軌跡データが空です"); enabled = false; return; }

        PrimitiveType prim = data.shape == "cylinder" ? PrimitiveType.Cylinder
                           : data.shape == "sphere" ? PrimitiveType.Sphere
                           : PrimitiveType.Cube;
        GameObject go = GameObject.CreatePrimitive(prim);
        go.name = "TrackedObject_" + data.label;
        Destroy(go.GetComponent<Collider>());   // 物理干渉なし（kinematic replay）
        go.transform.localScale = Vector3.one * data.size;
        var renderer = go.GetComponent<Renderer>();
        renderer.material.color = new Color(0.85f, 0.30f, 0.30f);
        target = go.transform;
        startTime = Time.time;
    }

    void Update()
    {
        if (data == null) return;
        if (Input.GetKeyDown(KeyCode.Space)) startTime = Time.time;
        // 矢印キーで同期を微調整: ← 物体を早める / → 物体を遅らせる
        if (Input.GetKeyDown(KeyCode.LeftArrow)) timeOffset += 0.1f;
        if (Input.GetKeyDown(KeyCode.RightArrow)) timeOffset -= 0.1f;

        float duration = data.frames[data.frames.Length - 1].t;
        float t = Time.time - startTime + timeOffset;
        if (t < 0f) t = loop ? t + duration : 0f;
        if (t > duration)
        {
            if (loop) { startTime = Time.time; t = 0f; }
            else t = duration;
        }
        // コマ間は再生側で線形補間（データは離散サンプルのまま）
        int i = 0;
        while (i < data.frames.Length - 2 && data.frames[i + 1].t < t) i++;
        TrajectoryFrame a = data.frames[i];
        TrajectoryFrame b = data.frames[Math.Min(i + 1, data.frames.Length - 1)];
        float u = b.t > a.t ? Mathf.Clamp01((t - a.t) / (b.t - a.t)) : 0f;
        target.position = Vector3.Lerp(ToUnity(a), ToUnity(b), u);
    }

    Vector3 ToUnity(TrajectoryFrame f)
        => new Vector3(mirrorX ? -f.x : f.x, f.y, f.z);

    void OnGUI()
    {
        // 同期調整用の状態表示（録画に入れたくない場合はこのメソッドを削除）
        GUI.Label(new Rect(10, Screen.height - 44, 500, 20),
            "Object sync: Space=restart  Arrow L/R=offset " +
            timeOffset.ToString("+0.0;-0.0") + "s");
    }
}
